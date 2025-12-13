import queue
import time
from typing import Tuple,Any

class TimestampTTSQueueHandle(queue.Queue):
    """
    一个自定义队列类，它在每个入队的元素上自动附加一个时间戳。
    """
    def put(self, item: Tuple[Any, Any, Any], block: bool = True, timeout: float | None = None) -> None:
        """
        重写 put 方法。
        
        Args:
            item: 原始的、不包含时间戳的数据元组 (SentenceType, audio_data, segment_text)。
            block: 与 queue.Queue.put() 中的同名参数含义相同。
            timeout: 与 queue.Queue.put() 中的同名参数含义相同。
        """
        # 1. 获取当前时间戳
        timestamp = time.perf_counter_ns()
        
        # 2. 将时间戳附加到原始元素后面，形成一个新的元组
        #    我们使用 *item 来解包原始元组
        new_item = (*item, timestamp)
        
        # 3. 调用父类（原始 Queue 类）的 put 方法，将新元素放入队列
        super().put(new_item, block=block, timeout=timeout)

