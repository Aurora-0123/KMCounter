from pathlib import Path


# Keep pytest's temporary files inside the checkout on restricted Windows hosts.
Path('.work').mkdir(exist_ok=True)
