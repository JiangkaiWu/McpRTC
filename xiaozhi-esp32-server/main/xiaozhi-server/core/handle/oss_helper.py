import oss2
import io
import os
from uuid import uuid4

# 初始化 OSS 客户端（记得改成你自己的配置）
auth = oss2.Auth('LTAI5tH6hrrCzDgG5FCKr8Ss', 'v6w1s2UsTQcqfmkrAAUNArE0WG1tCW')
bucket = oss2.Bucket(auth, 'https://oss-cn-beijing.aliyuncs.com', 'benchmark-generating')

def upload_frames_to_oss(frame_list, prefix="frames/", format="JPEG", expire_time=300):
    """
    上传帧到阿里 OSS，并返回临时签名 URL 列表。
    :param frame_list: List[PIL.Image.Image]
    :param prefix: OSS 上的存储前缀目录
    :param format: 图片格式
    :param expire_time: 签名 URL 有效期（秒）
    :return: (List[str], List[str]) (签名 URL 列表, object_key 列表)
    """
    urls = []
    object_keys = []
    for img in frame_list:
        buffer = io.BytesIO()
        img.save(buffer, format=format)
        buffer.seek(0)

        object_key = f"{prefix}{uuid4().hex}.jpg"
        bucket.put_object(object_key, buffer.getvalue())

        # 生成签名 URL（有效期 expire_time 秒）
        signed_url = bucket.sign_url('GET', object_key, expire_time)
        urls.append(signed_url)
        object_keys.append(object_key)
    return urls, object_keys

def upload_video_to_oss(local_file_path, prefix="videos/", expire_time=600):
    """
    上传本地视频文件到阿里 OSS，并返回临时签名 URL。

    :param local_file_path: str, 本地视频文件的完整路径
    :param prefix: str, OSS 上的存储前缀目录
    :param expire_time: int, 签名 URL 有效期（秒）
    :return: (str, str) or (None, None), (签名 URL, object_key)
    """
    object_keys = []
    # 检查本地文件是否存在
    if not os.path.exists(local_file_path):
        print(f"错误：文件 '{local_file_path}' 不存在。")
        return None, None

    # 从原始文件名中获取文件扩展名，例如 .mp4
    _, file_extension = os.path.splitext(local_file_path)
    
    # 创建一个唯一的对象名 (object_key)，并保留原始文件扩展名
    object_key = f"{prefix}{uuid4().hex}{file_extension}"
    object_keys.append(object_key)

    try:
        # 从本地文件上传，更适合大文件
        # print(f"正在上传 '{local_file_path}' 到 'oss://{bucket}/{object_key}'...")
        bucket.put_object_from_file(object_key, local_file_path)

        # 生成签名 URL（有效期 expire_time 秒）
        signed_url = bucket.sign_url('GET', object_key, expire_time)
        
        # print("上传成功！")
        return signed_url, object_keys

    except oss2.exceptions.OssError as e:
        print(f"上传到 OSS 时发生错误: {e}")
        return None, None

def delete_frames_from_oss(object_keys):
    """
    删除 OSS 上的帧文件
    :param object_keys: 上传时记录的 object_key 列表
    """
    for key in object_keys:
        bucket.delete_object(key)