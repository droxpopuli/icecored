from flask import Flask
from flask_restful import reqparse, abort, Api, Resource
from invoke import Context, Runner
from os.path import basename, splitext
import werkzeug
import json
import time
import math
import pkgutil
import struct
from threading import RLock, Thread
try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    import importlib_resources as pkg_resources

from . import res  # relative-import the *package* containing the templates

app = Flask(__name__)
api = Api(app)

parser = reqparse.RequestParser()
parser.add_argument('name')
parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')

command = Context()

class LED():
    C_RESET = "FF804D"
    C_BOOTLOADER = "4751B3"
    C_PROGRAMMING = "D4D7FF"
    C_RUNNING =  "78CC4B"

    @staticmethod
    def set_color(hex, divider=16):
        r, g, b = tuple(int(hex[i:i+2], 16) for i in (0, 2, 4))
        command.run(f"echo {math.floor(r/divider)} > /sys/class/leds/pca963x\:red/brightness")
        command.run(f"echo {math.floor(g/divider)} > /sys/class/leds/pca963x\:green/brightness")
        command.run(f"echo {math.floor(b/divider)} > /sys/class/leds/pca963x\:blue/brightness")

class Builder():
    root_path = "/usr/fpga"

    @staticmethod
    def write_resource(res_name):
        data = pkg_resources.read_text(res, res_name)
        with open(f'{Builder.root_path}/{res_name}', 'w') as f:
            f.write(data)

    @staticmethod
    def build_bitstream(file_name):
        append_log = f">>{Builder.root_path}/log.file 2>&1"

        # Make a new log file, unzip, prep makefile, run make, copy bitstream.
        command.run(f"truncate {Builder.root_path}/log.file -s 0")
        command.run(f"bsdtar -xvf {Builder.root_path}/{file_name}.zip -s'|[^/]*/||' {append_log}")
        Builder.write_resource("Makefile")
        command.run(f"make all PROJ={file_name} {append_log}")
        command.run(f"cp {file_name}.bin /data/ {append_log}")

    @staticmethod
    def get_build_log():
        response = {}
        if ".rpt" in command.run(f"ls {Builder.root_path}", warn=True).stdout:
            response["Build Report"] = command.run(f"cat {Builder.root_path}/*.rpt").stdout 
        else:
            response["Build Report"] = "No Build Reports found..."

        if command.run(f"test -f {Builder.root_path}/log.file", warn=True).ok:
            response["Build Log"] = command.run(f"cat {Builder.root_path}/log.file").stdout
        else:
            response["Build Log"] = "No Builds Performed..."

        return response

class BitStreams():
    @staticmethod
    def upload_bitstream(source_bin, file_name):
        source_bin.save(f"/data/{file_name}.bin")
        return file_name, 201

    @staticmethod
    def get_bitstream_list():
        result = command.run("ls /data/*.bin", warn=True)
        if result.failed:
            response = "No Bitstreams Found..."
        else:
            response = {
                "Bitstreams Found": len(result.stdout.splitlines()), 
                "BitStream List": [splitext(basename(file))[0] for file in result.stdout.splitlines()]
            }

        return response

class Board():
    fpga_lock = RLock()
    board_data = {}

    @staticmethod
    def program_bitstream(file_name):
        with Board.fpga_lock:
            # Reset FPGA and refresh board data.
            LED.set_color(LED.C_RESET)
            command.run("uhubctl -a 2 -p 3 -l 1-1")
            LED.set_color(LED.C_BOOTLOADER)
            time.sleep(1)
            Board.get_board_data(force_reload=True)
            LED.set_color(LED.C_PROGRAMMING)

            # Program the board
            if command.run(f"tinyprog -p /data/{file_name}.bin", warn=True).failed:
                # Reset it if we fail.
                LED.set_color(LED.C_RESET)
                command.run("uhubctl -a 2 -p 3 -l 1-1")
                Board.board_data["boardmeta"]["activeimage"] = "bootloader"
                LED.set_color(LED.C_BOOTLOADER)
                return 500
            else:
                LED.set_color(LED.C_RUNNING)
                Board.board_data["boardmeta"]["activeimage"] = file_name
                return file_name, 200

    @staticmethod
    def get_board_data(force_reload=False):
        if Board.board_data == {} or len(Board.board_data) == 0 or force_reload:
            data = json.loads(command.run(f"tinyprog -m").stdout)
            if len(data) > 0:
                Board.board_data = data[0]
                Board.board_data["boardmeta"]["activeimage"] = "Bootloader..."
            else:
                Board.board_data = "No Boards in Bootloader Mode..."
        return Board.board_data

class Dashboard(Resource):
    def get(self):
        response = {}
        response["Banner"] = "Welcome to IceCored 0.1.0-alpha!"
        response["FPGA Status"] =   Board.get_board_data()
        response["Bistream List"] = BitStreams.get_bitstream_list()
        response["Build Status"] =  Builder.get_build_log()
        response["Usage"] = {
                "/build" : {
                    "GET" : "Get the current build log output or if the build is complate, the build report.",
                    "PUT" : {
                        "About": "Send a $NAME.zip with a $NAME.v with a top level module (named top) to build and store.",
                        "file": "An octet stream assumed to be a zip file of verilog source."
                    }
                },
                "/bitstreams" : {
                    "GET" : "List out all bitstreams.",
                    "PUT" : {
                        "About": "Upload a bitstream directly.",
                        "file": "An octet stream assumed to be a yosys/arachne-pnr/icestorm made .bin file."
                    }
                },
                "/fpga" : {
                    "GET" : "Get JSON metadata of all attached FPGAs",
                    "PUT" : {
                        "About": "Program the FPGA with a sotred bitstream.",
                        "name": "The basename of the bitstream to program the FPGA with."
                    },
                    "/<bitstream_name>" : {
                        "GET" : "Program the FPGA with <bitstream_name>"
                    }
                }
            }
        return response


class Build(Resource):
    def get(self):
        return Builder.get_build_log()

    def put(self):
        args = parser.parse_args()
        source_name = splitext(basename(args['file'].filename))[0]

        command.run(f"rm -rf {Builder.root_path}/*", warn=True)
        args['file'].save(f"{Builder.root_path}/{source_name}.zip")

        x = Thread(target=Builder.build_bitstream, args=(source_name, ))
        x.start()

        return source_name, 201

class BitStreamList(Resource):
    def get(self):
        return BitStreams.get_bitstream_list()

    def put(self):
        args = parser.parse_args()

        bitstream_name = splitext(basename(args['file'].filename))[0]
        bitstream_data = args['file']

        return BitStreams.upload_bitstream(bitstream_data, bitstream_name)

class FPGA(Resource):
    def get(self):
        return Board.get_board_data()

    def post(self):
        args = parser.parse_args()
        bitstream_name = basename(args['name'])

        x = Thread(target=Board.program_bitstream, args=(bitstream_name,))
        x.start()

        return bitstream_name

class FPGAProgram(Resource):
    def get(self, bitstream_name):
        x = Thread(target=Board.program_bitstream, args=(bitstream_name,))
        x.start()

        return bitstream_name

api.add_resource(Dashboard, '/')
api.add_resource(Build, '/build')
api.add_resource(BitStreamList, '/bitstreams')
api.add_resource(FPGA, '/fpga')
api.add_resource(FPGAProgram, '/fpga/<bitstream_name>')

def run_debug():
    LED.set_color(LED.C_RESET)
    command.run("uhubctl -a 2 -p 3 -l 1-1")
    LED.set_color(LED.C_BOOTLOADER)
    app.run(debug=True, host="0.0.0.0", port=80)

def run_production():
    LED.set_color(LED.C_RESET)
    command.run("uhubctl -a 2 -p 3 -l 1-1")
    LED.set_color(LED.C_BOOTLOADER)
    app.run(debug=False, host="0.0.0.0", port=80)