/**
 * 通过<script src="/static/js/tools.js"></script>引入使用
 */


/**
 * RSA 加密类，提供基于 RSA-OAEP 的密钥生成、公钥导出、加密和解密功能。
 */
class RSA {
    /**
     * 创建 RSA 实例。
     * @param {string} [name="RSA-OAEP"] - 加密算法名称，默认 "RSA-OAEP"。
     * @param {string} [hash="SHA-256"] - 哈希算法名称，默认 "SHA-256"。
     */
    constructor(name = "RSA-OAEP", hash = "SHA-256") {
        /** @private {string} 加密算法名称 */
        this.name = name;
        /** @private {string} 哈希算法名称 */
        this.hash = hash;
        /** @private {CryptoKeyPair|null} 密钥对，包含公钥和私钥 */
        this.key = null;
    }

    /**
     * 初始化 RSA 密钥对，生成 2048 位密钥。
     * @returns {Promise<void>} 成功生成密钥对时返回，无返回值。
     * @throws {Error} 如果密钥生成失败，抛出错误。
     */
    async init() {
        try {
            this.key = await window.crypto.subtle.generateKey(
                {
                    name: this.name,
                    modulusLength: 2048,
                    publicExponent: new Uint8Array([0x01, 0x00, 0x01]), // 65537
                    hash: this.hash,
                },
                true, // 可导出
                ["encrypt", "decrypt"]
            );
        } catch (error) {
            console.error("密钥生成失败:", error);
            throw new Error("密钥生成失败");
        }
    }

    /**
     * 导出公钥为 PEM 格式。
     * @returns {Promise<string>} PEM 格式的公钥字符串。
     * @throws {Error} 如果公钥导出失败，抛出错误。
     */
    async getPublicKey_pem() {
        try {
            const spki = await window.crypto.subtle.exportKey("spki", this.key.publicKey);
            const b64 = this._arrayBufferToBase64(spki);
            const pem = b64.match(/.{1,64}/g).join('\n');
            return `-----BEGIN PUBLIC KEY-----\n${pem}\n-----END PUBLIC KEY-----`;
        } catch (error) {
            console.error("导出公钥失败:", error);
            throw new Error("导出公钥失败");
        }
    }

    /**
     * 使用公钥加密明文。
     * @param {string} plainText - 要加密的明文字符串。
     * @param {Object} [options] - 加密选项。
     * @param {string|null} [options.PublicKey_pem=null] - PEM 格式的公钥字符串。
     * @param {boolean} [options.use_myPublicKey=false] - 是否使用实例自身的公钥。
     * @param {string} [options.output="base64"] - 输出格式，可选 "base64" 或 "hex"。
     * @returns {Promise<string>} 加密后的密文（base64 或 hex 格式）。
     * @throws {Error} 如果加密失败或公钥无效，抛出错误。
     */
    async encrypt(plainText, { PublicKey_pem = null, use_myPublicKey = false, output = 'base64' } = {}) {
        try {
            const publicKey = await this._resolvePublicKey(PublicKey_pem, use_myPublicKey);
            const encoder = new TextEncoder();
            const data = encoder.encode(plainText);

            const encrypted = await window.crypto.subtle.encrypt({ name: this.name }, publicKey, data);
            const byteArray = new Uint8Array(encrypted);

            return output === 'hex'
                ? Array.from(byteArray).map(b => b.toString(16).padStart(2, '0')).join('')
                : this._arrayBufferToBase64(encrypted);
        } catch (error) {
            console.error("加密失败:", error);
            throw new Error("加密失败");
        }
    }

    /**
     * 使用私钥解密密文。
     * @param {string} cipherText - 要解密的密文（base64 或 hex 格式）。
     * @param {Object} [options] - 解密选项。
     * @param {string} [options.input="base64"] - 输入格式，可选 "base64" 或 "hex"。
     * @returns {Promise<string>} 解密后的明文字符串。
     * @throws {Error} 如果私钥未初始化或解密失败，抛出错误。
     */
    async decrypt(cipherText, { input = 'base64' } = {}) {
        try {
            if (!this.key?.privateKey) throw new Error("私钥未初始化");

            let byteArray;
            if (input === 'hex') {
                byteArray = new Uint8Array(cipherText.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
            } else {
                const binaryString = atob(cipherText);
                byteArray = new Uint8Array([...binaryString].map(c => c.charCodeAt(0)));
            }

            const decrypted = await window.crypto.subtle.decrypt({ name: this.name }, this.key.privateKey, byteArray);
            const decoder = new TextDecoder();
            return decoder.decode(decrypted);
        } catch (error) {
            console.error("解密失败:", error);
            throw new Error("解密失败");
        }
    }

    // ==========================
    // 私有辅助方法
    // ==========================

    /**
     * 解析公钥，优先使用提供的 PEM 公钥或实例自身的公钥。
     * @private
     * @param {string|null} pem - PEM 格式的公钥字符串。
     * @param {boolean} useMyKey - 是否使用实例自身的公钥。
     * @returns {Promise<CryptoKey>} 解析后的公钥。
     * @throws {Error} 如果公钥未初始化或 PEM 格式无效，抛出错误。
     */
    async _resolvePublicKey(pem, useMyKey) {
        if (useMyKey) {
            if (!this.key?.publicKey) throw new Error("公钥未初始化");
            return this.key.publicKey;
        }

        if (!pem) throw new Error("必须提供 PEM 格式公钥或启用 use_myPublicKey");

        try {
            const b64 = pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s+/g, '');
            const binaryDer = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            return await window.crypto.subtle.importKey(
                'spki',
                binaryDer.buffer,
                { name: this.name, hash: this.hash },
                false,
                ['encrypt']
            );
        } catch (error) {
            console.error("公钥导入失败:", error);
            throw new Error("无效的公钥 PEM 格式");
        }
    }

    /**
     * 将 ArrayBuffer 转换为 Base64 字符串。
     * @private
     * @param {ArrayBuffer} buffer - 要转换的 ArrayBuffer。
     * @returns {string} Base64 编码字符串。
     */
    _arrayBufferToBase64(buffer) {
        return btoa(String.fromCharCode(...new Uint8Array(buffer)));
    }
}

/**
 * EEC - 前端加密工具库
 * JavaScript版本的加密、解密、哈希和编码工具
 */
class Eec {
    /**
     * 哈希工具类
     */
    static Hash = class {
        /**
         * SHA256 哈希
         * @param {string} data - 要哈希的数据
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {Promise<string>} 哈希值的十六进制字符串
         */
        static async sha256(data, encoding = 'utf-8') {
            try {
                const encoder = new TextEncoder();
                const dataBuffer = encoder.encode(data);
                const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
                const hashArray = Array.from(new Uint8Array(hashBuffer));
                return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            } catch (error) {
                console.error('SHA256 error:', error);
                return '';
            }
        }

        /**
         * SHA512 哈希
         * @param {string} data - 要哈希的数据
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {Promise<string>} 哈希值的十六进制字符串
         */
        static async sha512(data, encoding = 'utf-8') {
            try {
                const encoder = new TextEncoder();
                const dataBuffer = encoder.encode(data);
                const hashBuffer = await crypto.subtle.digest('SHA-512', dataBuffer);
                const hashArray = Array.from(new Uint8Array(hashBuffer));
                return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            } catch (error) {
                console.error('SHA512 error:', error);
                return '';
            }
        }
    }

    /**
     * 字节转换工具类
     */
    static Bytes = class {
        /**
         * 字符串转字节数组
         * @param {string} data - 字符串数据
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {Uint8Array} 字节数组
         */
        static stb(data, encoding = 'utf-8') {
            try {
                const encoder = new TextEncoder();
                return encoder.encode(data);
            } catch (error) {
                console.error('String to bytes error:', error);
                return new Uint8Array();
            }
        }

        /**
         * 字节数组转字符串
         * @param {Uint8Array} data - 字节数组
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {string} 字符串
         */
        static bts(data, encoding = 'utf-8') {
            try {
                const decoder = new TextDecoder(encoding);
                return decoder.decode(data);
            } catch (error) {
                console.error('Bytes to string error:', error);
                return '';
            }
        }
    }

    /**
     * Base64 编码工具类
     */
    static B64 = class {
        /**
         * 字符串 Base64 编码
         * @param {string} data - 要编码的字符串
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {string} Base64编码的字符串
         */
        static encodeStr(data, encoding = 'utf-8') {
            try {
                const encoder = new TextEncoder();
                const bytes = encoder.encode(data);
                return btoa(String.fromCharCode(...bytes));
            } catch (error) {
                console.error('Base64 encode string error:', error);
                return '';
            }
        }

        /**
         * 字符串 Base64 解码
         * @param {string} data - Base64编码的字符串
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {string} 解码后的字符串
         */
        static decodeStr(data, encoding = 'utf-8') {
            try {
                const binaryString = atob(data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const decoder = new TextDecoder(encoding);
                return decoder.decode(bytes);
            } catch (error) {
                console.error('Base64 decode string error:', error);
                return '';
            }
        }

        /**
         * 字节数组 Base64 编码
         * @param {Uint8Array} data - 要编码的字节数组
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {string} Base64编码的字符串
         */
        static encodeBytes(data, encoding = 'utf-8') {
            try {
                return btoa(String.fromCharCode(...data));
            } catch (error) {
                console.error('Base64 encode bytes error:', error);
                return '';
            }
        }

        /**
         * 字节数组 Base64 解码
         * @param {string} data - Base64编码的字符串
         * @param {string} encoding - 编码格式，默认'utf-8'
         * @returns {Uint8Array} 解码后的字节数组
         */
        static decodeBytes(data, encoding = 'utf-8') {
            try {
                const binaryString = atob(data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                return bytes;
            } catch (error) {
                console.error('Base64 decode bytes error:', error);
                return new Uint8Array();
            }
        }
    }

    /**
     * AES 加密工具类
     */
    static Aes = class {
        /**
         * AES-GCM 模式加密工具类
         */
        static Gcm = class {
            /**
             * 字符串 AES-GCM 加密
             * @param {string} data - 要加密的字符串
             * @param {string} key - 加密密钥
             * @param {string} encoding - 编码格式，默认'utf-8'
             * @returns {Promise<Object>} 包含iv、data、tag的对象
             */
            static async encryptStr(data, key, encoding = 'utf-8') {
                try {
                    // 验证密钥长度
                    const keyBytes = new TextEncoder().encode(key);
                    if (![16, 24, 32].includes(keyBytes.length)) {
                        throw new Error("Invalid AES key length. Must be 16, 24, or 32 bytes.");
                    }

                    // 导入密钥
                    const cryptoKey = await crypto.subtle.importKey(
                        'raw',
                        keyBytes,
                        'AES-GCM',
                        false,
                        ['encrypt']
                    );

                    // 生成随机IV
                    const iv = crypto.getRandomValues(new Uint8Array(12));

                    // 加密数据
                    const encoder = new TextEncoder();
                    const dataBytes = encoder.encode(data);
                    const encrypted = await crypto.subtle.encrypt(
                        {
                            name: 'AES-GCM',
                            iv: iv
                        },
                        cryptoKey,
                        dataBytes
                    );

                    // 提取密文和认证标签
                    const encryptedArray = new Uint8Array(encrypted);
                    const ciphertext = encryptedArray.slice(0, -16);
                    const tag = encryptedArray.slice(-16);

                    return {
                        iv: btoa(String.fromCharCode(...iv)),
                        data: btoa(String.fromCharCode(...ciphertext)),
                        tag: btoa(String.fromCharCode(...tag))
                    };
                } catch (error) {
                    console.error('AES-GCM encrypt string error:', error);
                    return {};
                }
            }

            /**
             * 字符串 AES-GCM 解密
             * @param {string} data - 要解密的数据
             * @param {string} iv - 初始化向量
             * @param {string} tag - 认证标签
             * @param {string} key - 解密密钥
             * @param {string} encoding - 编码格式，默认'utf-8'
             * @returns {Promise<string>} 解密后的字符串
             */
            static async decryptStr(data, iv, tag, key, encoding = 'utf-8') {
                try {
                    // 验证密钥长度
                    const keyBytes = new TextEncoder().encode(key);
                    if (![16, 24, 32].includes(keyBytes.length)) {
                        throw new Error("Invalid AES key length. Must be 16, 24, or 32 bytes.");
                    }

                    // 导入密钥
                    const cryptoKey = await crypto.subtle.importKey(
                        'raw',
                        keyBytes,
                        'AES-GCM',
                        false,
                        ['decrypt']
                    );

                    // 解码Base64数据
                    const ivBytes = Uint8Array.from(atob(iv), c => c.charCodeAt(0));
                    const ciphertextBytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
                    const tagBytes = Uint8Array.from(atob(tag), c => c.charCodeAt(0));

                    // 合并密文和标签
                    const encryptedData = new Uint8Array(ciphertextBytes.length + tagBytes.length);
                    encryptedData.set(ciphertextBytes);
                    encryptedData.set(tagBytes, ciphertextBytes.length);

                    // 解密数据
                    const decrypted = await crypto.subtle.decrypt(
                        {
                            name: 'AES-GCM',
                            iv: ivBytes
                        },
                        cryptoKey,
                        encryptedData
                    );

                    const decoder = new TextDecoder(encoding);
                    return decoder.decode(decrypted);
                } catch (error) {
                    console.error('AES-GCM decrypt string error:', error);
                    return '';
                }
            }

            /**
             * 字节数组 AES-GCM 加密
             * @param {Uint8Array} data - 要加密的字节数组
             * @param {string} key - 加密密钥
             * @param {string} encoding - 编码格式，默认'utf-8'
             * @returns {Promise<Object>} 包含iv、data、tag的对象
             */
            static async encryptBytes(data, key, encoding = 'utf-8') {
                try {
                    // 验证密钥长度
                    const keyBytes = new TextEncoder().encode(key);
                    if (![16, 24, 32].includes(keyBytes.length)) {
                        throw new Error("Invalid AES key length. Must be 16, 24, or 32 bytes.");
                    }

                    // 导入密钥
                    const cryptoKey = await crypto.subtle.importKey(
                        'raw',
                        keyBytes,
                        'AES-GCM',
                        false,
                        ['encrypt']
                    );

                    // 生成随机IV
                    const iv = crypto.getRandomValues(new Uint8Array(12));

                    // 加密数据
                    const encrypted = await crypto.subtle.encrypt(
                        {
                            name: 'AES-GCM',
                            iv: iv
                        },
                        cryptoKey,
                        data
                    );

                    // 提取密文和认证标签
                    const encryptedArray = new Uint8Array(encrypted);
                    const ciphertext = encryptedArray.slice(0, -16);
                    const tag = encryptedArray.slice(-16);

                    return {
                        iv: btoa(String.fromCharCode(...iv)),
                        data: btoa(String.fromCharCode(...ciphertext)),
                        tag: btoa(String.fromCharCode(...tag))
                    };
                } catch (error) {
                    console.error('AES-GCM encrypt bytes error:', error);
                    return {};
                }
            }

            /**
             * 字节数组 AES-GCM 解密
             * @param {string} data - 要解密的数据
             * @param {string} iv - 初始化向量
             * @param {string} tag - 认证标签
             * @param {string} key - 解密密钥
             * @param {string} encoding - 编码格式，默认'utf-8'
             * @returns {Promise<Uint8Array>} 解密后的字节数组
             */
            static async decryptBytes(data, iv, tag, key, encoding = 'utf-8') {
                try {
                    // 验证密钥长度
                    const keyBytes = new TextEncoder().encode(key);
                    if (![16, 24, 32].includes(keyBytes.length)) {
                        throw new Error("Invalid AES key length. Must be 16, 24, or 32 bytes.");
                    }

                    // 导入密钥
                    const cryptoKey = await crypto.subtle.importKey(
                        'raw',
                        keyBytes,
                        'AES-GCM',
                        false,
                        ['decrypt']
                    );

                    // 解码Base64数据
                    const ivBytes = Uint8Array.from(atob(iv), c => c.charCodeAt(0));
                    const ciphertextBytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
                    const tagBytes = Uint8Array.from(atob(tag), c => c.charCodeAt(0));

                    // 合并密文和标签
                    const encryptedData = new Uint8Array(ciphertextBytes.length + tagBytes.length);
                    encryptedData.set(ciphertextBytes);
                    encryptedData.set(tagBytes, ciphertextBytes.length);

                    // 解密数据
                    const decrypted = await crypto.subtle.decrypt(
                        {
                            name: 'AES-GCM',
                            iv: ivBytes
                        },
                        cryptoKey,
                        encryptedData
                    );

                    return new Uint8Array(decrypted);
                } catch (error) {
                    console.error('AES-GCM decrypt bytes error:', error);
                    return new Uint8Array();
                }
            }
        }
    }
}
//
// // 使用示例
// async function example() {
//     const testData = "Hello, World!";
//     const key = "1234567890123456"; // 16字节密钥
//
//     try {
//         // 哈希示例
//         console.log("=== 哈希示例 ===");
//         const sha256Hash = await Eec.Hash.sha256(testData);
//         console.log("SHA256:", sha256Hash);
//
//         const sha512Hash = await Eec.Hash.sha512(testData);
//         console.log("SHA512:", sha512Hash);
//
//         // Base64编码示例
//         console.log("\n=== Base64编码示例 ===");
//         const encoded = Eec.B64.encodeStr(testData);
//         console.log("编码:", encoded);
//
//         const decoded = Eec.B64.decodeStr(encoded);
//         console.log("解码:", decoded);
//
//         // AES-GCM加密示例
//         console.log("\n=== AES-GCM加密示例 ===");
//         const encrypted = await Eec.Aes.Gcm.encryptStr(testData, key);
//         console.log("加密结果:", encrypted);
//
//         const decrypted = await Eec.Aes.Gcm.decryptStr(
//             encrypted.data,
//             encrypted.iv,
//             encrypted.tag,
//             key
//         );
//         console.log("解密结果:", decrypted);
//
//         // 字节转换示例
//         console.log("\n=== 字节转换示例 ===");
//         const bytes = Eec.Bytes.stb(testData);
//         console.log("字符串转字节:", bytes);
//
//         const backToString = Eec.Bytes.bts(bytes);
//         console.log("字节转字符串:", backToString);
//
//     } catch (error) {
//         console.error("示例执行错误:", error);
//     }
// }
//
// // 取消注释下面这行来运行示例
// // example();
//
