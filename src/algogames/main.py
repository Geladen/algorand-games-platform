from dotenv import load_dotenv
load_dotenv(dotenv_path='ops/env/preprod.env')

from game_platform.interact_platform import _create_platform, interact_platform

# _create_platform()
# interact_swap()
interact_platform()
