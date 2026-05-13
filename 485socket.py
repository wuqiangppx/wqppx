import socket
import time
import datetime
import csv
import os


# ============================================================
# TCP 配置
# ============================================================
HOST = "0.0.0.0"
PORT = 12345

# ============================================================
# 风速计 Modbus RTU 配置
# ============================================================
SLAVE_ID = 0x01          # 从机地址，说明书默认 1
FUNC_CODE = 0x03         # 读保持寄存器
WIND_REG_ADDR = 0x0004   # 风速寄存器地址
REG_COUNT = 0x0001       # 读取 1 个寄存器

READ_INTERVAL = 1.0      # 读取周期，单位秒
RECV_TIMEOUT = 2.0       # 接收超时时间，单位秒

CSV_FILE = "wind_speed_tcp_log.csv"


# ============================================================
# 时间函数
# ============================================================
def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def unix_ms():
    return int(time.time() * 1000)


# ============================================================
# Modbus RTU CRC16
# ============================================================
def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF

    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1

    return crc & 0xFFFF


def add_crc(frame: bytes) -> bytes:
    crc = modbus_crc16(frame)
    crc_low = crc & 0xFF
    crc_high = (crc >> 8) & 0xFF
    return frame + bytes([crc_low, crc_high])


def check_crc(frame: bytes) -> bool:
    if len(frame) < 5:
        return False

    data = frame[:-2]
    recv_crc = frame[-2] | (frame[-1] << 8)
    calc_crc = modbus_crc16(data)

    return recv_crc == calc_crc


# ============================================================
# 构造读取风速命令
# ============================================================
def build_read_wind_cmd() -> bytes:
    """
    按说明书读取风速寄存器 0x0004。

    主机查询命令：
    01 03 00 04 00 01 C5 CB
    """

    frame = bytes([
        SLAVE_ID,
        FUNC_CODE,
        (WIND_REG_ADDR >> 8) & 0xFF,
        WIND_REG_ADDR & 0xFF,
        (REG_COUNT >> 8) & 0xFF,
        REG_COUNT & 0xFF
    ])

    return add_crc(frame)


# ============================================================
# 接收数据
# ============================================================
def recv_response(conn: socket.socket, timeout: float = 2.0) -> bytes:
    """
    风速计正常响应长度为 7 字节：
    01 03 02 Data_H Data_L CRC_L CRC_H

    TCP 是流式协议，可能分包，所以这里循环接收。
    """

    conn.settimeout(timeout)

    buffer = bytearray()
    expected_len = 7

    while len(buffer) < expected_len:
        try:
            data = conn.recv(expected_len - len(buffer))
        except socket.timeout:
            break

        if not data:
            break

        buffer.extend(data)

    return bytes(buffer)


# ============================================================
# 解析风速计返回数据
# ============================================================
def parse_wind_response(response: bytes):
    """
    正常响应格式：
    01 03 02 03 E8 B8 FA

    其中：
    01      从机地址
    03      功能码
    02      数据长度，2 字节
    03 E8   风速原始值，十进制 1000
    B8 FA   CRC，低字节在前

    风速 = 原始值 / 100
    单位：m/s
    """

    if len(response) == 0:
        return None, "未收到数据"

    if len(response) != 7:
        return None, f"返回长度错误，期望 7 字节，实际 {len(response)} 字节，HEX={response.hex(' ').upper()}"

    if not check_crc(response):
        return None, f"CRC 校验失败，HEX={response.hex(' ').upper()}"

    slave_id = response[0]
    func_code = response[1]
    byte_count = response[2]

    if slave_id != SLAVE_ID:
        return None, f"从机地址错误，期望 {SLAVE_ID}，实际 {slave_id}"

    if func_code != FUNC_CODE:
        return None, f"功能码错误，期望 0x03，实际 0x{func_code:02X}"

    if byte_count != 2:
        return None, f"数据字节数错误，期望 2，实际 {byte_count}"

    raw_value = (response[3] << 8) | response[4]
    wind_speed = raw_value / 100.0

    return {
        "slave_id": slave_id,
        "func_code": func_code,
        "raw_value": raw_value,
        "wind_speed": wind_speed,
        "unit": "m/s"
    }, None


# ============================================================
# CSV 日志
# ============================================================
def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "time",
                "unix_ms",
                "g815r_ip",
                "g815r_port",
                "raw_value",
                "wind_speed_m_s",
                "request_hex",
                "response_hex"
            ])


def save_csv(addr, result, request: bytes, response: bytes):
    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            now_str(),
            unix_ms(),
            addr[0],
            addr[1],
            result["raw_value"],
            f"{result['wind_speed']:.2f}",
            request.hex(" ").upper(),
            response.hex(" ").upper()
        ])


# ============================================================
# 处理 G815R TCP 连接
# ============================================================
def handle_g815r(conn: socket.socket, addr):
    print("\n" + "=" * 80)
    print(f"[{now_str()}] G815R 已连接")
    print(f"G815R 地址：{addr[0]}:{addr[1]}")
    print("=" * 80)

    request_cmd = build_read_wind_cmd()

    print(f"读取风速命令：{request_cmd.hex(' ').upper()}")

    if request_cmd.hex(" ").upper() == "01 03 00 04 00 01 C5 CB":
        print("命令校验：与说明书一致")
    else:
        print("命令校验：与说明书不一致，请检查 CRC")

    try:
        while True:
            # 1. 发送读取风速命令
            conn.sendall(request_cmd)

            print("\n" + "-" * 80)
            print(f"时间       ：{now_str()}")
            print(f"发送查询   ：{request_cmd.hex(' ').upper()}")

            # 2. 接收风速计响应
            response = recv_response(conn, RECV_TIMEOUT)

            print(f"收到响应   ：{response.hex(' ').upper() if response else '无响应'}")

            # 3. 解析响应
            result, error = parse_wind_response(response)

            if error:
                print(f"解析状态   ：失败")
                print(f"失败原因   ：{error}")
            else:
                print(f"解析状态   ：成功")
                print(f"从机地址   ：{result['slave_id']}")
                print(f"功能码     ：0x{result['func_code']:02X}")
                print(f"原始值     ：{result['raw_value']}")
                print(f"风速       ：{result['wind_speed']:.2f} m/s")

                save_csv(addr, result, request_cmd, response)

            time.sleep(READ_INTERVAL)

    except ConnectionResetError:
        print(f"[{now_str()}] G815R 连接被重置")

    except BrokenPipeError:
        print(f"[{now_str()}] G815R 连接已断开")

    except Exception as e:
        print(f"[{now_str()}] 程序异常：{e}")

    finally:
        conn.close()
        print(f"[{now_str()}] 连接关闭：{addr[0]}:{addr[1]}")


# ============================================================
# TCP Server 主程序
# ============================================================
def main():
    init_csv()

    print("=" * 80)
    print("风速计 Modbus RTU over TCP 读取程序")
    print("说明：G815R 作为 TCP Client，电脑作为 TCP Server")
    print(f"监听地址：{HOST}:{PORT}")
    print(f"从机地址：0x{SLAVE_ID:02X}")
    print(f"风速寄存器：0x{WIND_REG_ADDR:04X}")
    print(f"CSV日志：{os.path.abspath(CSV_FILE)}")
    print("=" * 80)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # 防止程序重启后端口占用
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((HOST, PORT))
    server.listen(1)

    print("等待 G815R 连接...")

    while True:
        conn, addr = server.accept()
        handle_g815r(conn, addr)
        print("等待 G815R 重新连接...")


if __name__ == "__main__":
    main()