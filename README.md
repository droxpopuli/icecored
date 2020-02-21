# icecored
RESTful API Server for building bitstreams for ice40 FPGAs and programming tinyprog-capable boards.
 
Read the post here: http://drox.zone/2020/02/21/Internet-of-Chips/

Goto the IP and you get:

```json
{
  "Banner": "Welcome to IceCored 0.1.0-alpha!",
  "FPGA Status": {
    "boardmeta": {
      "name": "TinyFPGA BX",
      "fpga": "ice40lp8k-cm81",
      "hver": "1.0.0",
      "uuid": "690ae3fe-3b71-4ee6-afd7-13de8ff09f3c",
      "activeimage": "Bootloader..."
    },
    "bootmeta": {
      "bootloader": "TinyFPGA USB Bootloader",
      "bver": "1.0.1",
      "update": "https://tinyfpga.com/update/tinyfpga-bx",
      "addrmap": {
        "bootloader": "0x000a0-0x28000",
        "userimage": "0x28000-0x50000",
        "userdata": "0x50000-0x100000"
      }
    },
    "port": "/dev/ttyACM0"
  },
  "Bitstream List": {
    "Bitstreams Found": 0,
    "BitStream List": []
  },
  "Build Status": {
    "Build Report": "No Build Reports found...",
    "Build Log": "No Builds Performed..."
  },
  "Usage": {
    "/build": {
      "GET": "Get the current build log output or if the build is complate, the build report.",
      "PUT": {
        "About": "Send a $NAME.zip with a $NAME.v with a top level module (named top) to build and store.",
        "file": "An octet stream assumed to be a zip file of verilog source."
      }
    },
    "/bitstreams": {
      "GET": "List out all bitstreams.",
      "PUT": {
        "About": "Upload a bitstream directly.",
        "file": "An octet stream assumed to be a yosys/arachne-pnr/icestorm made .bin file."
      }
    },
    "/fpga": {
      "GET": "Get JSON metadata of all attached FPGAs",
      "PUT": {
        "About": "Program the FPGA with a stored bitstream.",
        "name": "The basename of the bitstream to program the FPGA with."
      },
      "/<bitstream_name>": {
        "GET": "Program the FPGA with <bitstream_name>"
      }
    }
  }
}
```
