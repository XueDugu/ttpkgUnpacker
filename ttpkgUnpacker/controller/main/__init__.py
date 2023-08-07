import os

from model.mpk import MPK

class Main:
    def __init__(self, args):
        # 初始化 Main 类，传入命令行参数 args
        self._args = args

    def run(self):
        # 主程序运行方法
        if len(self._args) < 2:
            print("Use :python3 main.py js/xxx.ttpkg.js")
            exit()  # 如果没有传入文件路径参数，则打印使用方法并退出程序

        for arg in self._args[1:]:
            with open(arg, 'rb') as io:
                _, file_arg = os.path.split(arg)
                print('Loading: %s' % arg)  # 打印正在加载的文件路径
                mpk = MPK.load(io)  # 加载 MPK 文件，返回 MPK 对象
                for i in mpk.files:
                    # 循环处理 MPK 文件中的每个文件
                    file = mpk.file(i)  # 获取当前文件的信息字典
                    if file['offset'] != 0:
                        # 如果文件的偏移量不为 0，则表示该文件需要解压缩
                        if file['name'] == '':
                            file['name'] = 'unknown_%s' % i  # 如果文件名为空，则设置为默认值
                        print('Unpacking: %s' % file['name'])  # 打印当前正在解压缩的文件名
                        path_file = '%s_unpack/%s' % (arg, file['name'])  # 拼接解压缩后的文件路径
                        dir_file, _ = os.path.split(path_file)  # 获取文件所在目录路径
                        os.makedirs(dir_file, exist_ok=True)  # 创建目录（如果不存在），存在时不报错
                        with open(path_file, 'wb') as io_file:
                            # 打开解压缩后的文件，以二进制写入模式
                            io_file.write(mpk.data(i))  # 写入当前文件的数据到文件中
