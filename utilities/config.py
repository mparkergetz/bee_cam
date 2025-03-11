import configparser

class Config(configparser.ConfigParser):

    def __init__(self, config_path='/home/pi/bee_cam/config.ini'):
        super().__init__()
        self.read(config_path)

    def print(self):
        for section in self.sections():
            print(section)
            for k,v in self[section].items():
                print(f'  {k} = {self.clean_value(v)}')
    
    def clean_value(self, value):
        return value.split("#", 1)[0].strip()

    def dict(self):
        config_dict = {}
        for section in self.sections():
            config_dict[section] = {k: self.clean_value(v) for k, v in self[section].items()}
        return config_dict

 

# -----------------------------------------------------------------------------
if __name__ == '__main__':
    config = Config()
    config.print()
    print(config.dict())
