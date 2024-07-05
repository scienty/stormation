import argparse
import os, sys, logging
from functools import partial

from botocore import args

here = os.path.abspath(os.path.dirname(__file__))
get_path = partial(os.path.join, here)

def init():
  logging.basicConfig(level=logging.INFO)
  logging.getLogger('boto3').setLevel(logging.INFO)
  logging.getLogger('botocore').setLevel(logging.INFO)

  console = logging.StreamHandler()
  console.setLevel(logging.DEBUG)
  logging.getLogger('').addHandler(console)

def main():
  parser = argparse.ArgumentParser(description="Stormation to manage cloud formation!")

  parser.add_argument("command", choices=["create", "update", "delete"])

  parser.add_argument("-b", "--bundle", type=str, nargs=1,
                      metavar="bundle_name", required=True,
                      help="Stormation bundle file to process.")

  parser.add_argument("-s", "--stack", type=str, nargs=1,
                      metavar="stack_name", default=None,
                      help="Stack name in the bundle to processs.")

  args = parser.parse_args(sys.argv[1:])

  command = args.command
  bundleFile = get_path(args.bundle[0])
  stackName = args.stack[0] if args.stack else None

  from cfn.cfn_bundle import CFBundle
  bundle = CFBundle(bundleFile)

  if command == "create":
      bundle.create_update_bundle()
  elif command == "update":
      bundle.update(stackName)
  else:
      bundle.delete(stackName)

if __name__ == '__main__':
  init()
  main()