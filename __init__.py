from calibre.customize import InterfaceActionBase


PLUGIN_NAME = "HTML Generator"
PLUGIN_SAFE_NAME = PLUGIN_NAME.strip().lower().replace(' ', '_')
PLUGIN_DESCRIPTION = 'A plugin to convert epub file to one single html file'
PLUGIN_VERSION_TUPLE = (1, 1, 0)
PLUGIN_VERSION = '.'.join([str(x) for x in PLUGIN_VERSION_TUPLE])
PLUGIN_AUTHORS = 'Ynjxsjmh'


class ActionHTML(InterfaceActionBase):

    name = PLUGIN_NAME
    version = PLUGIN_VERSION_TUPLE
    author = PLUGIN_AUTHORS
    supported_platforms = ['windows', 'osx', 'linux']
    description = PLUGIN_DESCRIPTION
    minimum_calibre_version = (6, 0, 0)

    def cli_main(self, argv):
        #Typical Usage: calibre-debug --run-plugin "HTML Generator" -- -h
        from calibre_plugins.html_generator.main import main as html_generator_main
        html_generator_main(argv[1:], self.version, usage='%prog --run-plugin '+'\"self.name\"'+' --')
