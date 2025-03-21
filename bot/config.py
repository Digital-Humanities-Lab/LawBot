import configparser

def load_config(file_path="config.txt"):
    """Function to read the configuration from the config.txt file."""
    config = configparser.ConfigParser()
    with open(file_path, 'r') as f:
        config_string = '[DEFAULT]\n' + f.read()
    config.read_string(config_string)
    return config['DEFAULT']

