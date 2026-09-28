import paddle

print("Paddle版本:")
print(paddle.__version__)


print("CUDA是否可用:")
print(paddle.device.is_compiled_with_cuda())


print("当前设备:")
print(paddle.device.get_device())
