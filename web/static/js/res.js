
class Res{
    static rs = class{
        static async work(){
            try {
                // 初始化 RSA 密钥对
                S.rsa = new RSA();
                await S.rsa.init();
                S.pubPem = await S.rsa.getPublicKey_pem();

                // 发送 RSA 公钥到 /rs 端点
                const form = new FormData();
                form.append("user_key_pub_pem", S.pubPem);
                const res = await fetch("/rs", {
                    method: "POST",
                    body: form
                });

                if (!res.ok) {
                    throw new Error(`HTTP 错误: ${res.status}`);
                }

                const result = await res.json();

                // 解密返回的 AES 密钥
                const encryptedKey = result.data;
                S.aes_key = await S.rsa.decrypt(encryptedKey, { input: "hex" });
                return true;
            } catch (e) {
                console.error("RSA 密钥交换错误:", e);
                return false;
            }
            
            

        }
        
    }
    
    static api = class{
        /**
         * 发送加密请求到 /api 端点
         * @param {string} operate - 操作名称
         * @param {object} args - 操作参数
         * @param {string} algorithm - 压缩算法 ("gzip", "zlib", "zstd", "lzma" 或 "")
         * @param {string} message - 可选的请求消息
         * @returns {Promise<[any, string, number]>} - [解密后的数据, 提示消息, 响应代码]
         */
        static async work(operate, args ={}, algorithm="", message=""){
            try {
                this.check()
                // 构造第二层业务数据
                const secondLayer = { operate, args };
                const jsonString = JSON.stringify(secondLayer);

                let content
                if (!algorithm){
                    // 无压缩：直接加密 JSON 字符串
                    content = await Eec.Aes.Gcm.encryptStr(jsonString, S.aes_key);
                }else {
                    // // 压缩 JSON 字符串后再加密
                    // let compressedData;
                    // const jsonBytes = new TextEncoder().encode(jsonString);
                    //
                    // switch (algorithm.toLowerCase()) {
                    //     case "gzip":
                    //         compressedData = pako.gzip(jsonBytes);
                    //         break;
                    //     case "zlib":
                    //         compressedData = pako.deflate(jsonBytes);
                    //         break;
                    //     case "zstd":
                    //         if (!ZstdCodec) throw new Error("ZstdCodec 未加载");
                    //         const zstd = new ZstdCodec.Compression();
                    //         compressedData = zstd.compress(jsonBytes);
                    //         break;
                    //     case "lzma":
                    //         if (!LZMA) throw new Error("LZMA 未加载");
                    //         compressedData = await new Promise((resolve, reject) => {
                    //             LZMA.compress(jsonBytes, 6, (result, error) => {
                    //                 if (error) reject(error);
                    //                 else resolve(new Uint8Array(result));
                    //             });
                    //         });
                    //         break;
                    //     default:
                    //         throw new Error(`不支持的压缩算法: ${algorithm}`);
                    // }
                    // // 加密压缩后的数据
                    // content = await Eec.Aes.Gcm.encryptBytes(compressedData, S.aes_key);

                }

                // 构造第一层负载
                const firstLayer = {
                    message: message,
                    compression: algorithm !== "",
                    algorithm: algorithm,
                    content: content
                };
                const jsonPayload = JSON.stringify(firstLayer);
                S.session_user = await Eec.Hash.sha256(S.aes_key);
                // 发送请求到 /api 端点
                const res = await fetch("/api", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "session_user": S.session_user
                    },
                    credentials: "include", // 发送 Cookie
                    body: jsonPayload
                });
                if (!res.ok) {
                    throw new Error(`HTTP 错误: ${res.status}`);
                }
                const result = await res.json();
                // 解密响应
                const { data, iv, tag } = result.data;
                const decryptedJson = await Eec.Aes.Gcm.decryptStr(data, iv, tag, S.aes_key);
                const parsed = JSON.parse(decryptedJson);
                S.aes_key = parsed.key;
                return [parsed.data, result.message, result.code];
            } catch (e) {
                return [false, "error", 999];
            }
        }
        static check() {
            // 验证加密通道
            if (!S.aes_key || !S.session_user) {
                throw new Error("无有效的加密通道（缺少 AES 密钥或会话用户）");
            }
        }
        
    }
}


