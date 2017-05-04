# TE Sushi Chef

### Step 0: Installation

* [Install pip](https://pypi.python.org/pypi/pip) if you don't have it already.
* [Install Python3](https://www.python.org/downloads) if you don't have it already
* [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) if you don't have it already
* Optional: install and activate a virtual environment
* Open a terminal
* Run `git clone https://github.com/jayoshih/te-sushi-chef.git`
* Run `cd te-sushi-chef`
* Run `pip install -r requirements.txt`

### Step 1: Obtaining an Authorization Token ###
You will need an authorization token to create a channel on Kolibri Studio. In order to obtain one:

1. Create an account on [Kolibri Studio](https://contentworkshop.learningequality.org/).
2. Navigate to the Tokens tab under your Settings page.
3. Copy the given authorization token (you will need this for later).

### Step 2: Running the chef ###
 * Open te-sushi-chef/chef/data/data.py
 * Change SOURCE_DOMAIN to your name (you only need to change this once)
 * Change SOURCE_ID to your username (you only need to change this once)
 * Run `python -m chef.py --token=<token>`, replacing `<token>` with the token you copied earlier
