class AverageLatencyAnalyzer:
    """
    一个用于在线计算平均延迟的类。
    """
    def __init__(self):
        """
        初始化分析器。
        """
        self.packet_count = 0
        self.average_latency = 0.0

    def update(self, latency):
        """
        用一个新的延迟数据点来更新平均延迟。

        参数:
            latency (float): 单个包的传输延迟。
        """
        self.packet_count += 1
        # 同样使用在线平均算法公式
        self.average_latency = self.average_latency + (latency - self.average_latency) / self.packet_count

    def get_average_latency(self):
        """
        获取当前的平均延迟。

        返回:
            float: 当前所有包的平均延迟。
        """
        return self.average_latency

    def get_packet_count(self):
        """
        获取已经处理的包的数量。

        返回:
            int: 包的数量。
        """
        return self.packet_count

import queue
import threading
import time
import atexit
import csv # 引入csv模块

class MultiMetricLatencyLogger:
    """
    一个支持多指标记录的、线程安全的、基于缓冲区的日志记录器。
    将数据以CSV格式写入文件。
    """
    def __init__(self, filepath="metrics_log.csv", buffer_size=8192, flush_interval=5):
        self.filepath = filepath
        self.flush_interval = flush_interval
        self.buffer = queue.Queue(maxsize=buffer_size)
        self._stop_event = threading.Event()

        # 初始化CSV文件并写入表头
        try:
            with open(self.filepath, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["metric_name", "value_ms"])
        except IOError as e:
            print(f"错误: 无法初始化日志文件 {self.filepath}: {e}")

        self._writer_thread = threading.Thread(target=self._file_writer, daemon=True)
        self._writer_thread.start()
        
        atexit.register(self.shutdown)
        print(f"多指标日志记录器已启动，将数据写入 '{self.filepath}'")

    def log(self, metric_name, value_ms):
        """
        记录一条带有指标名称的延迟数据。
        
        :param metric_name: 指标的名称 (e.g., "uplink", "downlink")
        :param value_ms: 延迟的数值 (毫秒)
        """
        try:
            # 将数据以元组形式放入队列
            self.buffer.put_nowait((metric_name, value_ms))
        except queue.Full:
            print(f"警告: 指标 {metric_name} 的日志缓冲区已满，可能丢失数据。")

    def _file_writer(self):
        while not self._stop_event.is_set():
            time.sleep(self.flush_interval)
            
            data_to_write = []
            while not self.buffer.empty():
                try:
                    data_to_write.append(self.buffer.get_nowait())
                except queue.Empty:
                    break
            
            if data_to_write:
                try:
                    # 使用 'a' (追加) 模式写入
                    with open(self.filepath, "a", newline='') as f:
                        writer = csv.writer(f)
                        writer.writerows(data_to_write)
                except IOError as e:
                    print(f"错误: 无法写入日志文件 {self.filepath}: {e}")

    def shutdown(self):
        print("正在关闭多指标日志记录器，清空缓冲区...")
        self._stop_event.set()
        
        final_data = []
        while not self.buffer.empty():
            try:
                final_data.append(self.buffer.get_nowait())
            except queue.Empty:
                break
        
        if final_data:
            try:
                with open(self.filepath, "a", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerows(final_data)
                print(f"{len(final_data)} 条剩余日志已写入文件。")
            except IOError as e:
                print(f"错误: 关闭时无法写入日志文件 {self.filepath}: {e}")
        
        print("日志记录器已关闭。")