from io import FileIO, SEEK_CUR
from util.io_helper import IOHelper

MPK_MAGIC = 'TPKG'  # 文件类型名
MPK_VERSION = 131072  # 文件的版本号

class MPK:
    def __init__(self, io):
        self._io = io
        self._files = []  # 用于存储文件中各个文件的信息
        self._version = MPK_VERSION  # 文件的版本

    @staticmethod
    def printTell(io):
        print(io.tell())  # 打印当前文件指针的位置

    @staticmethod
    def load(io: FileIO):
        instance = MPK(io)
        magic = IOHelper.read_ascii_string(io, 4)  # 从文件中读取 4 字节的魔法值
        if magic == MPK_MAGIC:
            version = IOHelper.read_struct(io, '<i')[0]  # 从文件中读取版本号
            MPK.printTell(io)  # 打印当前文件指针的位置
            io.seek(4, SEEK_CUR)  # 跳过 4 字节，用于处理其他信息
            MPK.printTell(io)  # 打印当前文件指针的位置
            count = IOHelper.read_struct(io, 'i')[0]  # 从文件中读取文件数量
            instance.set_version(version)  # 设置文件实例的版本号
            for i in range(count):
                if i == 0:
                    size = 'i'  # 第一个文件的 name_length 采用 'i' 大小
                else:
                    size = 'i'  # 其他文件的 name_length 采用 'i' 大小
                name_length = IOHelper.read_struct(io, size)[0]  # 从文件中读取文件名长度
                file_data = IOHelper.read_struct(io, '<'+str(name_length)+'s')[0]  # 读取文件名数据
                file_name = bytes(file_data).decode(encoding='ascii')  # 将文件名数据转换为字符串
                offset = IOHelper.read_struct(io, '=i')[0]  # 从文件中读取文件数据偏移位置
                data_size = IOHelper.read_struct(io, '=i')[0]  # 从文件中读取文件数据大小
                print(file_name)  # 打印文件名
                instance.insert_file({
                    'is_zip': False,
                    'index': i,
                    'offset': offset,
                    'data_size': data_size,
                    'name': file_name,
                    'data': None,
                })

        return instance

    def set_version(self, version):
        self._version = version  # 设置文件实例的版本号

    def insert_file(self, file, index=None):
        i = 0
        if index is None:
            i = len(self._files)
        self._files.insert(i, file)  # 向 _files 列表中插入文件信息

    def data(self, index):
        if index < len(self._files):
            file = self._files[index]  # 获取指定索引处的文件信息
            if file['data'] is None:
                if not file['is_zip']:
                    data = IOHelper.read_range(self._io, file['offset'], file['data_size'])  # 从文件中读取文件数据
                    file['data'] = data
                else:
                    raise Exception('Unsupport File.')  # 不支持的文件类型，这里抛出异常
            else:
                data = file['data']

            return data  # 返回文件数据

    def file(self, index):
        if index < len(self._files):
            file = self._files[index].copy()
            file.pop('data')
            return file  # 返回指定索引处的文件信息（不包含文件数据）

    @property
    def files(self):
        return [i for i in range(len(self._files))]  # 返回包含文件索引的列表
