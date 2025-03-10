import configparser

class Config(configparser.ConfigParser):

    def __init__(self):
        super().__init__()
        self.read('/home/pi/weather_test_scripts/config.ini')

    def print(self):
        for section in self.sections():
            print(section)
            for k,v in self[section].items():
                print(f'  {k} = {v}')

    def dict(self):
        config_dict = {}
        for section in self.sections():
            config_dict[section] = dict(self[section])
        return config_dict

 

# -----------------------------------------------------------------------------
if __name__ == '__main__':
    config = Config()
    config.print()
    print(config.dict())
