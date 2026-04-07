import struct


class IOHelper:
    @staticmethod
    def read_exact(io, size):
        data = io.read(size)
        if len(data) != size:
            raise EOFError(f"Expected {size} bytes, got {len(data)}")
        return data

    @staticmethod
    def read_struct(io, fmt):
        data = IOHelper.read_exact(io, struct.calcsize(fmt))
        return struct.unpack(fmt, data)

    @staticmethod
    def read_ascii_string(io, size):
        return IOHelper.read_exact(io, size).decode("ascii")

    @staticmethod
    def read_range(io, offset=0, size=-1):
        io.seek(offset)
        return io.read(size)

    @staticmethod
    def write_struct(io, fmt, *values):
        data = struct.pack(fmt, *values)
        return io.write(data)

    @staticmethod
    def write_ascii_string(io, content):
        data = content.encode("ascii") + b"\x00"
        return io.write(data)
