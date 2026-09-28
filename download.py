from modelscope import snapshot_download


model_dir = snapshot_download(
    "Qwen/Qwen3-4B-Instruct-2507",
    cache_dir="/root/autodl-tmp/models"
)

print("模型保存到：", model_dir)