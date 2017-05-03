
"""Usage: chef [--token=<t>]

Options:
  --token=<t>                 Authorization token (can be token or path to file with token) [default: #]

"""

from ricecooker.commands import uploadchannel
from docopt import docopt

if __name__ == '__main__':
    arguments = docopt(__doc__)
    uploadchannel("chef/chef.py", token=arguments['--token'], verbose=True, reset=True, warn=True)
