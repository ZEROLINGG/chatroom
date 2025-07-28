import zlib
import gzip
import bz2
import lzma
import base64
import time
import statistics
import random
import json
from io import BytesIO
import string
from tabulate import tabulate
from colorama import init, Fore, Style

# 初始化 colorama
init(autoreset=True)

# 生成不同类型的测试数据
def generate_test_data():
    repetitive_data = ("This is a test message. " * 50).encode()
    random_data = ''.join(random.choices(string.ascii_letters + string.digits, k=1000)).encode()
    json_data = json.dumps({
        "users": [{"id": i, "name": f"User_{i}", "data": f"Sample data {i}"} for i in range(50)]
    }).encode()
    return [
        ("Repetitive Text", repetitive_data),
        ("Random Data", random_data),
        ("JSON Data", json_data)
    ]

# 动态选择单位
def format_size(size):
    return f"{size / 1024:.2f} KB" if size >= 1024 else f"{size:.0f} bytes"

# 压缩和编码测试函数
def run_compression_test(data_name, data, num_runs=5):
    results = {
        "Base64": [],
        "zlib": [],
        "gzip": [],
        "bz2": [],
        "lzma": []
    }
    original_size = len(data)
    print(f"\n{Fore.CYAN}=== 测试数据: {data_name} (原始大小: {format_size(original_size)}) ===")

    for i in range(num_runs):
        print(f"{Fore.YELLOW}运行 {i+1}/{num_runs}...")
        # 1. Base64 编码
        start = time.time()
        b64_encoded = base64.b64encode(data)
        end = time.time()
        results["Base64"].append({
            "encoded_size": len(b64_encoded),
            "time_ms": (end - start) * 1000,
            "decoded_correct": base64.b64decode(b64_encoded) == data
        })

        # 2. zlib 压缩 + Base64
        start = time.time()
        compressed = zlib.compress(data)
        mid = time.time()
        b64_encoded = base64.b64encode(compressed)
        end = time.time()
        try:
            decompressed = zlib.decompress(base64.b64decode(b64_encoded))
            decoded_correct = decompressed == data
        except Exception:
            decoded_correct = False
        results["zlib"].append({
            "compressed_size": len(compressed),
            "encoded_size": len(b64_encoded),
            "compress_time_ms": (mid - start) * 1000,
            "encode_time_ms": (end - mid) * 1000,
            "total_time_ms": (end - start) * 1000,
            "decoded_correct": decoded_correct
        })

        # 3. gzip 压缩 + Base64
        start = time.time()
        gzip_buffer = BytesIO()
        with gzip.GzipFile(fileobj=gzip_buffer, mode='wb') as f:
            f.write(data)
        compressed = gzip_buffer.getvalue()
        mid = time.time()
        b64_encoded = base64.b64encode(compressed)
        end = time.time()
        try:
            gzip_buffer = BytesIO(base64.b64decode(b64_encoded))
            with gzip.GzipFile(fileobj=gzip_buffer, mode='rb') as f:
                decompressed = f.read()
            decoded_correct = decompressed == data
        except Exception:
            decoded_correct = False
        results["gzip"].append({
            "compressed_size": len(compressed),
            "encoded_size": len(b64_encoded),
            "compress_time_ms": (mid - start) * 1000,
            "encode_time_ms": (end - mid) * 1000,
            "total_time_ms": (end - start) * 1000,
            "decoded_correct": decoded_correct
        })

        # 4. bz2 压缩 + Base64
        start = time.time()
        compressed = bz2.compress(data)
        mid = time.time()
        b64_encoded = base64.b64encode(compressed)
        end = time.time()
        try:
            decompressed = bz2.decompress(base64.b64decode(b64_encoded))
            decoded_correct = decompressed == data
        except Exception:
            decoded_correct = False
        results["bz2"].append({
            "compressed_size": len(compressed),
            "encoded_size": len(b64_encoded),
            "compress_time_ms": (mid - start) * 1000,
            "encode_time_ms": (end - mid) * 1000,
            "total_time_ms": (end - start) * 1000,
            "decoded_correct": decoded_correct
        })

        # 5. lzma 压缩 + Base64
        start = time.time()
        compressed = lzma.compress(data)
        mid = time.time()
        b64_encoded = base64.b64encode(compressed)
        end = time.time()
        try:
            decompressed = lzma.decompress(base64.b64decode(b64_encoded))
            decoded_correct = decompressed == data
        except Exception:
            decoded_correct = False
        results["lzma"].append({
            "compressed_size": len(compressed),
            "encoded_size": len(b64_encoded),
            "compress_time_ms": (mid - start) * 1000,
            "encode_time_ms": (end - mid) * 1000,
            "total_time_ms": (end - start) * 1000,
            "decoded_correct": decoded_correct
        })

    print_results(data_name, original_size, results, num_runs)

# 优化打印结果
def print_results(data_name, original_size, results, num_runs):
    headers = ["方法", "压缩大小", "编码后大小", "压缩时间 (ms)", "编码时间 (ms)", "总时间 (ms)", "数据完整性"]
    table_data = []
    best_compressed_size = float('inf')
    best_total_time = float('inf')
    best_method_size = ""
    best_method_time = ""

    for method in results:
        color = {
            "Base64": Fore.BLUE,
            "zlib": Fore.GREEN,
            "gzip": Fore.YELLOW,
            "bz2": Fore.MAGENTA,
            "lzma": Fore.CYAN
        }.get(method, Fore.WHITE)

        if method == "Base64":
            encoded_sizes = [r["encoded_size"] for r in results[method]]
            times = [r["time_ms"] for r in results[method]]
            integrity = all(r["decoded_correct"] for r in results[method])
            avg_encoded = statistics.mean(encoded_sizes)
            std_encoded = statistics.stdev(encoded_sizes) if len(encoded_sizes) > 1 else 0
            avg_time = statistics.mean(times)
            std_time = statistics.stdev(times) if len(times) > 1 else 0
            if avg_encoded < best_compressed_size:
                best_compressed_size = avg_encoded
                best_method_size = method
            if avg_time < best_total_time:
                best_total_time = avg_time
                best_method_time = method
            table_data.append([
                f"{color}{method}{Style.RESET_ALL}",
                "N/A",
                f"{format_size(avg_encoded)} (±{std_encoded:.2f})",
                "N/A",
                f"{avg_time:.2f} (±{std_time:.2f})",
                f"{avg_time:.2f} (±{std_time:.2f})",
                f"{Fore.GREEN if integrity else Fore.RED}{integrity}{Style.RESET_ALL}"
            ])
        else:
            compressed_sizes = [r["compressed_size"] for r in results[method]]
            encoded_sizes = [r["encoded_size"] for r in results[method]]
            compress_times = [r["compress_time_ms"] for r in results[method]]
            encode_times = [r["encode_time_ms"] for r in results[method]]
            total_times = [r["total_time_ms"] for r in results[method]]
            integrity = all(r["decoded_correct"] for r in results[method])
            avg_compressed = statistics.mean(compressed_sizes)
            avg_encoded = statistics.mean(encoded_sizes)
            std_compressed = statistics.stdev(compressed_sizes) if len(compressed_sizes) > 1 else 0
            std_encoded = statistics.stdev(encoded_sizes) if len(encoded_sizes) > 1 else 0
            avg_compress = statistics.mean(compress_times)
            std_compress = statistics.stdev(compress_times) if len(compress_times) > 1 else 0
            avg_encode = statistics.mean(encode_times)
            std_encode = statistics.stdev(encode_times) if len(encode_times) > 1 else 0
            avg_total = statistics.mean(total_times)
            std_total = statistics.stdev(total_times) if len(total_times) > 1 else 0
            if avg_compressed < best_compressed_size:
                best_compressed_size = avg_compressed
                best_method_size = method
            if avg_total < best_total_time:
                best_total_time = avg_total
                best_method_time = method
            table_data.append([
                f"{color}{method}{Style.RESET_ALL}",
                f"{format_size(avg_compressed)} (±{std_compressed:.2f})",
                f"{format_size(avg_encoded)} (±{std_encoded:.2f})",
                f"{avg_compress:.2f} (±{std_compress:.2f})",
                f"{avg_encode:.2f} (±{std_encode:.2f})",
                f"{avg_total:.2f} (±{std_total:.2f})",
                f"{Fore.GREEN if integrity else Fore.RED}{integrity}{Style.RESET_ALL}"
            ])

    print(f"\n{Fore.CYAN}--- {data_name} 测试结果汇总 ({num_runs} 次运行) ---")
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid", stralign="center", numalign="center"))

    # 最佳方法总结
    print(f"\n{Fore.GREEN}最佳压缩大小: {best_method_size} ({format_size(best_compressed_size)})")
    print(f"{Fore.GREEN}最短总时间: {best_method_time} ({best_total_time:.2f} ms)")

# 主程序
def main():
    test_data = generate_test_data()
    for data_name, data in test_data:
        try:
            run_compression_test(data_name, data)
        except Exception as e:
            print(f"{Fore.RED}测试 {data_name} 时发生错误: {e}")

if __name__ == "__main__":
    main()