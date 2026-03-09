__license__ = 'GPL 3'

from calibre.customize import InterfaceActionBase


class HTMLGeneratorLibraryPlugin(InterfaceActionBase):
    """Main calibre UI plugin.

    Adds a toolbar/menu action to export selected books to a single HTML file.
    """

    name = 'HTML Generator - Library Export'
    description = 'Export selected books to a single self-contained HTML file'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Ynjxsjmh'
    version = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    # Load the GUI code only in GUI context
    actual_plugin = 'calibre_plugins.html_generator_library.ui:HTMLGeneratorLibraryInterfaceAction'
