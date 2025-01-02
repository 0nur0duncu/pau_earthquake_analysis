# -*- coding: utf-8 -*-

import os.path
from PyQt5 import sip

from qgis.core import (
    Qgis, QgsVectorLayer, QgsProject, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsPalLayerSettings,
    QgsTextFormat, QgsVectorLayerSimpleLabeling, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsSymbol, QgsRendererRange, QgsGraduatedSymbolRenderer,
    QgsMarkerSymbol, QgsTextBufferSettings
)
from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface
from qgis.gui import QgsProjectionSelectionDialog

# Import the code for the dialog
from .widgets.EarthquakeAnalysisDialog import EarthquakeAnalysisDialog

# Ana eklenti sınıfı - QGIS ile entegrasyonu sağlar
class EarthquakeAnalysisPlugin(QtCore.QObject):

    def __init__(self, iface):
        super(EarthquakeAnalysisPlugin, self).__init__()
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.first_start = True
        self.dialog = None
        self._earthquake_layer = None  # Özel değişken olarak tanımla
        self.actions = []
        # Layer kaldırıldığında tetiklenecek sinyal bağlantısı
        QgsProject.instance().layerRemoved.connect(self.on_layer_removed)

    @property
    def earthquake_layer(self):
        """Earthquake layer için güvenli erişim"""
        if hasattr(self, '_earthquake_layer') and self._earthquake_layer is not None:
            if not sip.isdeleted(self._earthquake_layer):
                return self._earthquake_layer
        return None
        
    @earthquake_layer.setter
    def earthquake_layer(self, layer):
        """Earthquake layer için güvenli atama"""
        self._earthquake_layer = layer

    def on_layer_removed(self, layer_id):
        """Layer kaldırıldığında çağrılır"""
        try:
            if self.dialog and hasattr(self.dialog, 'vector_layer') and self.dialog.vector_layer:
                if not sip.isdeleted(self.dialog.vector_layer):
                    if layer_id == self.dialog.vector_layer.id():
                        self.dialog.vector_layer = None
                        self.dialog.ilComboBox.clear()
                        self.dialog.ilceComboBox.clear()
            
            current_layer = self.earthquake_layer
            if current_layer is not None and layer_id == current_layer.id():
                self.earthquake_layer = None
        except:
            # Herhangi bir hata durumunda referansları temizle
            if hasattr(self.dialog, 'vector_layer'):
                self.dialog.vector_layer = None
            self.earthquake_layer = None

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Toolbar ve menü öğelerini eklemek için yardımcı metod"""
        
        icon = QIcon(icon_path)
        action = QtWidgets.QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar = self.iface.addToolBar('Deprem Analizi')
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                'Deprem Analizi',
                action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon", "Pamukkale_University_logo.svg")
        self.add_action(
            icon_path,
            text=self.tr("Deprem Analizi"),
            callback=self.showDialog,
            parent=self.iface.mainWindow())
        
        # Dialog'u oluştur
        self.dialog = EarthquakeAnalysisDialog()
        # Deprem verisi sinyalini bağla
        self.dialog.earthquakeDataFiltered.connect(self.update_earthquake_points)
        
        # Earthquake layer referansı
        self.earthquake_layer = None

    def tr(self, message):
        """Metinleri çevirmek için yardımcı metod"""
        return QtCore.QCoreApplication.translate('EarthquakeAnalysisPlugin', message)

    def update_earthquake_points(self, earthquake_data):
        """Deprem noktalarını güncelle"""
        try:
            # Eğer önceki deprem katmanı varsa kaldır
            if self.earthquake_layer and not sip.isdeleted(self.earthquake_layer):
                QgsProject.instance().removeMapLayer(self.earthquake_layer.id())
                self.earthquake_layer = None
            
            # Aynı isimli diğer katmanları da temizle
            for layer in QgsProject.instance().mapLayersByName("Depremler"):
                if layer.id() in QgsProject.instance().mapLayers():
                    QgsProject.instance().removeMapLayer(layer.id())
            
            if earthquake_data is not None and not earthquake_data.empty:
                # Yeni deprem katmanı oluştur
                uri = "Point?crs=epsg:4326&field=id:integer&field=date:string&field=magnitude:double&field=depth:double&field=area:string"
                earthquake_layer = QgsVectorLayer(uri, "Depremler", "memory")
                provider = earthquake_layer.dataProvider()
                
                # Özellikleri ekle
                features = []
                for idx, row in earthquake_data.iterrows():
                    feature = QgsFeature()
                    point = QgsGeometry.fromPointXY(QgsPointXY(float(row['longitude']), float(row['latitude'])))
                    feature.setGeometry(point)
                    feature.setAttributes([
                        int(row['eventId']),
                        row['eventDate'].strftime('%Y-%m-%d %H:%M:%S'),
                        float(row['magnitude']),
                        float(row['depth']),
                        str(row['area'])
                    ])
                    features.append(feature)
                
                provider.addFeatures(features)
                
                # Stil ayarla
                symbol = QgsMarkerSymbol.createSimple({
                    'name': 'circle',
                    'color': '#FF4136',  # Koyu kırmızı
                    'size': '3',
                    'outline_style': 'solid',
                    'outline_width': '0.5',
                    'outline_color': '#800000'  # Bordo kenar
                })
                earthquake_layer.renderer().setSymbol(symbol)
                
                # Etiketleme ayarları
                label_settings = QgsPalLayerSettings()
                text_format = QgsTextFormat()
                text_format.setSize(8)
                text_format.setColor(QColor(0, 0, 0))  # Siyah metin
                
                buffer_settings = QgsTextBufferSettings()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(1)
                buffer_settings.setColor(QColor(255, 255, 255, 230))  # Yarı saydam beyaz arka plan
                text_format.setBuffer(buffer_settings)
                
                label_settings.setFormat(text_format)
                label_settings.fieldName = "magnitude"
                label_settings.placement = QgsPalLayerSettings.OverPoint
                
                layer_settings = QgsVectorLayerSimpleLabeling(label_settings)
                earthquake_layer.setLabeling(layer_settings)
                earthquake_layer.setLabelsEnabled(True)
                
                # Katmanı haritaya ekle
                QgsProject.instance().addMapLayer(earthquake_layer, False)  # False ile layer tree'ye otomatik eklemeyi engelle
                
                # Layer tree'yi al ve deprem katmanını fay hatlarının altına ekle
                root = QgsProject.instance().layerTreeRoot()
                root.insertLayer(1, earthquake_layer)  # 1 indeksi ile fay hatlarının altına ekle
                
                self.earthquake_layer = earthquake_layer
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                None,
                "Hata",
                f"Deprem katmanı güncellenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )

    def unload(self):
        """Eklentiyi kaldır"""
        for action in self.actions:
            self.iface.removePluginMenu(
                'Deprem Analizi',
                action)
            self.iface.removeToolBarIcon(action)
        if hasattr(self, 'toolbar'):
            del self.toolbar

    def create_earthquake_layer(self, earthquake_data):
        """Deprem verilerinden nokta katmanı oluştur"""
        if earthquake_data is None or earthquake_data.empty:
            return None

        # Seçili koordinat sistemini al
        target_crs = self.dialog.target_crs

        # Geçici memory layer oluştur
        layer_name = "Depremler"
        layer = QgsVectorLayer(f"Point?crs={target_crs.authid()}", layer_name, "memory")
        provider = layer.dataProvider()

        # Alanları tanımla
        fields = [
            QgsField("eventId", QVariant.String),
            QgsField("eventDate", QVariant.String),
            QgsField("depth", QVariant.Double),
            QgsField("magnitudeType", QVariant.String),
            QgsField("magnitude", QVariant.Double),
            QgsField("area", QVariant.String)
        ]
        provider.addAttributes(fields)
        layer.updateFields()

        # Özellikleri ekle
        features = []
        source_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        
        for _, row in earthquake_data.iterrows():
            feat = QgsFeature()
            # WGS84'ten seçili koordinat sistemine dönüşüm yap
            point = QgsPointXY(float(row['longitude']), float(row['latitude']))
            if target_crs.authid() != 'EPSG:4326':
                transformed_point = transform.transform(point)
                feat.setGeometry(QgsGeometry.fromPointXY(transformed_point))
            else:
                feat.setGeometry(QgsGeometry.fromPointXY(point))
            
            feat.setAttributes([
                str(row['eventId']),
                str(row['eventDate']),
                float(row['depth']),
                str(row['magnitudeType']),
                float(row['magnitude']),
                str(row['area'])
            ])
            features.append(feat)

        provider.addFeatures(features)
        layer.updateExtents()
        return layer

    def showDialog(self):
        if not self.dialog:
            self.dialog = EarthquakeAnalysisDialog(self.iface.mainWindow())
            
        self.dialog.show()
        result = self.dialog.exec_()
        
        if result:
            try:
                # İl seçimi kontrolü
                if not self.dialog.ilComboBox.currentText():
                    return
                    
                # İlçe katmanını ekle
                if self.dialog.vector_layer and self.dialog.vector_layer.isValid():
                    filter_exp = self.dialog.get_filter_expression()
                    if filter_exp:
                        self.dialog.vector_layer.setSubsetString(filter_exp)
                    
                    # Katmanı projeye ekle
                    QgsProject.instance().addMapLayer(self.dialog.vector_layer)

                # Deprem verilerini işle (eğer varsa)
                filtered_earthquake_data = self.dialog.apply_earthquake_filter()
                if filtered_earthquake_data is not None:
                    # Eğer önceki deprem katmanı varsa kaldır
                    current_layer = self.earthquake_layer
                    if current_layer is not None:
                        QgsProject.instance().removeMapLayer(current_layer.id())
                        self.earthquake_layer = None

                    # Yeni deprem katmanını oluştur ve ekle
                    new_layer = self.create_earthquake_layer(filtered_earthquake_data)
                    if new_layer and new_layer.isValid():
                        self.earthquake_layer = new_layer
                        QgsProject.instance().addMapLayer(new_layer)
                        # Stil ayarlarını yap
                        self.style_earthquake_layer(new_layer)
            except Exception as e:
                # Hata durumunda kullanıcıyı bilgilendir
                QtWidgets.QMessageBox.critical(
                    self.iface.mainWindow(),
                    "Hata",
                    f"İşlem sırasında bir hata oluştu: {str(e)}",
                    QtWidgets.QMessageBox.Ok
                )

    def style_earthquake_layer(self, layer):
        """Deprem katmanına stil uygula"""
        if not layer or not self.dialog:
            return

        # Özel stil ayarlarını uygula
        # Sabit büyüklük aralıkları ve renkler tanımla
        magnitude_ranges = [
            (0, 2, QColor(255, 255, 0, 180)),    # Sarı (düşük risk)
            (2, 3, QColor(255, 165, 0, 180)),    # Turuncu (orta-düşük risk)
            (3, 4, QColor(255, 69, 0, 180)),     # Kırmızı-turuncu (orta risk)
            (4, 5, QColor(255, 0, 0, 180)),      # Kırmızı (yüksek risk)
            (5, 10, QColor(139, 0, 0, 180))      # Bordo (çok yüksek risk)
        ]

        # Graduated Symbol Renderer oluştur
        ranges = []
        for min_mag, max_mag, color in magnitude_ranges:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            # Sembol rengini ayarla
            symbol.setColor(color)
            # Dış çeper rengini ve kalınlığını ayarla
            symbol_layer = symbol.symbolLayer(0)
            symbol_layer.setStrokeColor(QColor(0, 0, 0))  # Siyah dış çeper
            symbol_layer.setStrokeWidth(0.5)  # Dış çeper kalınlığı
            # Büyüklüğe göre sembol boyutu ayarla
            size = 2 + (max_mag - min_mag)  # Basit ve hızlı boyut hesaplama
            symbol.setSize(size)
            range_label = f"{min_mag}-{max_mag}"
            magnitude_range = QgsRendererRange(min_mag, max_mag, symbol, range_label)
            ranges.append(magnitude_range)

        renderer = QgsGraduatedSymbolRenderer('magnitude', ranges)
        renderer.setMode(QgsGraduatedSymbolRenderer.Custom)  # Custom mod kullan
        layer.setRenderer(renderer)

        # Etiket ayarları
        layer_settings = QgsPalLayerSettings()
        layer_settings.fieldName = 'magnitude'
        layer_settings.enabled = True
        layer_settings.placement = QgsPalLayerSettings.AroundPoint
        layer_settings.dist = 2

        text_format = QgsTextFormat()
        text_format.setSize(8)
        text_format.setColor(QColor(0, 0, 0))  # Siyah metin rengi
        layer_settings.setFormat(text_format)

        layer.setLabeling(QgsVectorLayerSimpleLabeling(layer_settings))
        layer.setLabelsEnabled(True)

        layer.triggerRepaint()
