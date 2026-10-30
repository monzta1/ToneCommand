"""Read-only firmware migration report; never imports or opens a MIDI device."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devices.axefx3.registry import Registry
from devices.axefx3 import firmware_parity,fw33_profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware',default=fw33_profile.KEY)
    parser.add_argument('--variant',choices=('mk1','mk2'),default='mk2')
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args();reg=Registry(args.firmware);reg.hardware_variant=args.variant
    result=firmware_parity.report(reg)
    print(json.dumps(result,indent=2,ensure_ascii=True))
    if not result['recognized']:return 2
    return 1 if args.require_complete and not result['functionality_complete'] else 0


if __name__=='__main__':raise SystemExit(main())
