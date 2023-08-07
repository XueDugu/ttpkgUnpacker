from io import FileIO, SEEK_CUR

from util.io_helper import IOHelper

MPK_MAGIC = 'TPKG'
MPK_VERSION = 131072

class MPK:
    def __init__(self, io):
        # 初始化 MPK 对象，io 是文件流对象
        self._io = io
        self._files = []  # 存储文件信息的列表
        self._version = MPK_VERSION  # 默认 MPK 版本

    @staticmethod
    def printTell(io):
        # 辅助方法，打印当前文件流的位置
        print(io.tell())

    @staticmethod
    def load(io: FileIO):
        # 加载并解析 MPK 文件
        instance = MPK(io)  # 创建 MPK 类的实例
        magic = IOHelper.read_ascii_string(io, 4)  # 读取前 4 个字节作为 ASCII 字符串
        if magic == MPK_MAGIC:
            version = IOHelper.read_struct(io, '<i')[0]  # 读取接下来的 4 个字节作为小端整数
            MPK.printTell(io)  # 打印当前文件流的位置
            io.seek(4, SEEK_CUR)  # 将光标向前移动 4 个字节（跳过 magic 字符串）
            MPK.printTell(io)  # 打印当前文件流的位置
            count = IOHelper.read_struct(io, 'i')[0]  # 读取接下来的 4 个字节作为整数（文件数量）
            instance.set_version(version)  # 设置实例的 MPK 版本
            for i in range(count):
                # 循环处理每个 MPK 文件条目
                size = 'i'
                name_length = IOHelper.read_struct(io, size)[0]  # 读取接下来的 4 个字节作为整数（文件名长度）
                if i == 0:
                    io.seek(3, SEEK_CUR)  # 将光标向前移动 3 个字节（跳过未知数据）
                file_data = IOHelper.read_struct(io, '<' + str(name_length) + 's')[0]  # 读取文件名数据
                file_name = bytes(file_data).decode(encoding='utf-8')  # 将文件名字节解码为 UTF-8 字符串
                offset = IOHelper.read_struct(io, '=i')[0]  # 读取接下来的 4 个字节作为大端整数（文件偏移量）
                data_size = IOHelper.read_struct(io, '=i')[0]  # 读取接下来的 4 个字节作为大端整数（数据大小）
                print(file_name)  # 打印当前文件的名称
                instance.insert_file({
                    'is_zip': False,
                    'index': i,
                    'offset': offset,
                    'data_size': data_size,
                    'name': file_name,
                    'data': None,
                })  # 将文件信息插入实例的文件列表中

        return instance

    def set_version(self, version):
        # 设置 MPK 版本的方法
        self._version = version

    def insert_file(self, file, index=None):
        # 将文件条目插入文件列表的方法
        i = 0
        if index is None:
            i = len(self._files)
        self._files.insert(i, file)

    def data(self, index):
        # 获取文件数据的方法，通过文件索引
        if index < len(self._files):
            file = self._files[index]  # 获取文件信息的字典
            if file['data'] is None:
                if not file['is_zip']:
                    data = IOHelper.read_range(self._io, file['offset'], file['data_size'])  # 读取文件数据
                    file['data'] = data  # 将文件数据缓存到字典中
                else:
                    raise Exception('Unsupport File.')  # 不支持 zip 文件，抛出异常
            else:
                data = file['data']

            return data

    def file(self, index):
        # 获取文件信息的方法，通过文件索引
        if index < len(self._files):
            file = self._files[index].copy()  # 创建文件信息字典的副本
            file.pop('data')  # 从字典中删除 'data' 键（不需要保存文件数据）
            return file

    @property
    def files(self):
        # 属性，获取所有文件索引的列表
        return [i for i in range(len(self._files))]
