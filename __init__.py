# -*- coding: utf-8 -*-

def classFactory(iface):

    from .EarthquakeAnalysisPlugin import EarthquakeAnalysisPlugin
    return EarthquakeAnalysisPlugin(iface)
