# -*- coding: utf-8 -*-

from qgis.PyQt import QtWidgets, uic, QtCore
from qgis.PyQt.QtCore import pyqtSignal, QTimer
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis, QgsVectorLayer, QgsProject, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsPalLayerSettings,
    QgsTextFormat, QgsVectorLayerSimpleLabeling, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsSymbol, QgsRendererRange, QgsGraduatedSymbolRenderer,
    QgsMarkerSymbol, QgsTextBufferSettings, QgsFillSymbol, QgsSingleSymbolRenderer,
    QgsFeatureRequest
)
from qgis.utils import iface
import os
import unicodedata
import pandas as pd
import numpy as np

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "..", "ui", "ui_EarthquakeAnalysisDialog.ui")
)

class EarthquakeAnalysisDialog(QtWidgets.QDialog, FORM_CLASS):
    closingPlugin = pyqtSignal()
    earthquakeDataFiltered = pyqtSignal(object)  # Yeni sinyal
    
    def __init__(self, parent=None):
        super(EarthquakeAnalysisDialog, self).__init__(parent)
        self.setupUi(self)
        
        # UI elemanlarını düzenle
        self.setWindowTitle("Deprem Analizi")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        # Başlangıçta tüm grupları devre dışı bırak (ilçe sınırları hariç)
        self.earthquakeGroup.setEnabled(False)
        self.filterGroup.setEnabled(False)
        self.faultLinesGroup.setEnabled(False)
        self.settlementGroup.setEnabled(False)
        
        # Başlangıçta yakınlık mesafesi alanını devre dışı bırak
        self.bufferSpinBox.setEnabled(False)
        self.bufferLabel.setEnabled(False)
        
        # Başlangıçta sütun seçme alanlarını devre dışı bırak
        self.ilColumnComboBox.setEnabled(False)
        self.ilceColumnComboBox.setEnabled(False)
        self.ilColumnLabel.setEnabled(False)
        self.ilceColumnLabel.setEnabled(False)
        
        # Yıl filtresi alanlarını başlangıçta devre dışı bırak
        self.yearComboBox.setEnabled(False)
        self.endYearComboBox.setEnabled(False)
        self.yearRangeLabel.setEnabled(False)
        
        # Büyüklük filtresi alanlarını başlangıçta devre dışı bırak
        self.minMagnitudeSpinBox.setEnabled(False)
        self.maxMagnitudeSpinBox.setEnabled(False)
        self.magnitudeRangeLabel.setEnabled(False)
        self.magnitudeSeparatorLabel.setEnabled(False)
        
        # Başlangıçta yerleşim noktaları alanlarını devre dışı bırak
        self.settlementIlColumnComboBox.setEnabled(False)
        self.settlementIlceColumnComboBox.setEnabled(False)
        self.settlementIlLabel.setEnabled(False)
        self.settlementIlceLabel.setEnabled(False)
        self.settlementDistanceSpinBox.setEnabled(False)
        
        # Tamam butonunu başlangıçta devre dışı bırak
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        
        # Yerleşim noktaları katmanı için değişken
        self.settlement_layer = None
        self.settlement_file_path = None
        
        # Sinyalleri bağla
        self.filePathButton.clicked.connect(self.select_shapefile)
        self.csvFileButton.clicked.connect(self.select_csv_file)
        self.faultLineFileButton.clicked.connect(self.select_fault_line_file)
        self.ilComboBox.currentTextChanged.connect(self.update_ilce_combobox)
        self.ilceComboBox.currentTextChanged.connect(self.on_ilce_changed)
        self.showLabelsCheckBox.stateChanged.connect(self.update_layer_name)
        self.buttonBox.accepted.connect(self.validate_and_accept)
        self.buttonBox.rejected.connect(self.reject)
        self.bufferSpinBox.valueChanged.connect(self.on_buffer_changed)
        self.settlementDistanceSpinBox.valueChanged.connect(self.on_settlement_distance_changed)
        
        # Yıl filtresi sinyallerini bağla
        self.yearComboBox.currentTextChanged.connect(self.on_year_changed)
        self.endYearComboBox.currentTextChanged.connect(self.on_year_changed)
        
        # ComboBox placeholder metinleri
        self.ilComboBox.setPlaceholderText("İl seçiniz...")
        self.ilceComboBox.setPlaceholderText("İlçe seçiniz...")
        
        self.vector_layer = None
        self.original_layer_name = ""
        self.iface = iface
        self.file_path = None
        self.csv_file_path = None
        self.fault_line_layer = None
        self.earthquake_data = None
        self.earthquake_points = None
        self.target_crs = QgsCoordinateReferenceSystem('EPSG:32635')
        
        # Cache için değişkenler
        self.cached_geometry = None
        self.cached_filter_exp = None
        self.cached_buffer_distance = None
        
        # Buttonbox metinlerini güncelle
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setText("Tamam")
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText("İptal")
        
        # Add a default color for the layer to ensure consistency
        self.default_layer_color = QColor(255, 128, 0)  # Orange color
        self.fault_line_color = QColor(255, 0, 0)  # Red color for fault lines
        
        # Buffer layer reference
        self.buffer_layer = None
        
        # Sinyalleri bağla
        self.settlementFileButton.clicked.connect(self.select_settlement_file)
        
    def normalize_text(self, text):
        """Metni normalize et (büyük/küçük harf ve türkçe karakter duyarsız)"""
        # Türkçe karakterleri İngilizce karakterlere çevir
        tr_chars = {'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
                   'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C'}
        for tr_char, eng_char in tr_chars.items():
            text = text.replace(tr_char, eng_char)
        # Büyük harfe çevir ve unicode normalize et
        return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        
    def create_new_layer(self, file_path):
        """Yeni bir layer oluştur"""
        if file_path and os.path.exists(file_path):
            # Layer'ı seçilen koordinat sisteminde oluştur
            new_layer = QgsVectorLayer(file_path, self.original_layer_name, "ogr")
            if new_layer.isValid():
                if new_layer.crs() != self.target_crs:
                    # Koordinat dönüşümü için yeni bir memory layer oluştur
                    uri = f"polygon?crs={self.target_crs.authid()}"
                    memory_layer = QgsVectorLayer(uri, self.original_layer_name, "memory")
                    
                    # Alan özelliklerini kopyala
                    provider = memory_layer.dataProvider()
                    attrs = new_layer.fields()
                    provider.addAttributes(attrs)
                    memory_layer.updateFields()
                    
                    # Dönüşüm için transform oluştur
                    transform = QgsCoordinateTransform(
                        new_layer.crs(),
                        self.target_crs,
                        QgsProject.instance()
                    )
                    
                    # Özellikleri dönüştürerek kopyala
                    features = []
                    for feature in new_layer.getFeatures():
                        new_feature = feature
                        geom = feature.geometry()
                        geom.transform(transform)
                        new_feature.setGeometry(geom)
                        features.append(new_feature)
                    
                    provider.addFeatures(features)
                    memory_layer.updateExtents()
                    
                    # Set the default color
                    symbol = QgsFillSymbol.createSimple({'color': self.default_layer_color.name()})
                    new_layer.renderer().setSymbol(symbol)
                    
                    return memory_layer
                    
                return new_layer
        return None
        
    def ensure_valid_layer(self):
        """Layer'ın geçerli olduğundan emin ol, değilse yeniden yükle"""
        if not self.vector_layer or not self.vector_layer.isValid():
            new_layer = self.create_new_layer()
            if new_layer:
                self.vector_layer = new_layer
                return True
            return False
        return True
        
    def zoom_to_layer(self, filter_exp=None):
        """Haritayı verilen layer'a göre zoom yapar"""
        if not self.vector_layer or not self.ensure_valid_layer():
            return
            
        # Buffer alanını da hesaba katarak extent hesapla
        extent = None
        if self.buffer_layer and self.buffer_layer.isValid():
            extent = self.buffer_layer.extent()
        else:
            extent = self.vector_layer.extent()
            
        if not extent:
            return
            
        # Extent'i biraz genişlet
        extent.scale(1.1)  # %10 daha geniş görünüm
        
        # Canvas'ı güncelle
        if self.iface and self.iface.mapCanvas():
            self.iface.mapCanvas().setExtent(extent)
            self.iface.mapCanvas().refresh()
            
    def select_shapefile(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "İlçeler Shapefile Seç",
            "",
            "Shapefile (*.shp)"
        )
        
        if file_path and os.path.exists(file_path):
            self.file_path = file_path
            self.filePathEdit.setText(file_path)
            self.original_layer_name = os.path.splitext(os.path.basename(file_path))[0].lower()
            self.load_layer(file_path)
            
            # Shapefile seçildiğinde sütun seçme alanlarını aktif hale getir
            self.ilColumnComboBox.setEnabled(True)
            self.ilceColumnComboBox.setEnabled(True)
            self.ilColumnLabel.setEnabled(True)
            self.ilceColumnLabel.setEnabled(True)
            
            # Diğer alanları aktif hale getir
            self.enable_fields()
            
    def load_layer(self, file_path):
        new_layer = self.create_new_layer(file_path)
        if not new_layer:
            QtWidgets.QMessageBox.critical(self, "Hata", "Shapefile yüklenemedi!")
            return
            
        self.vector_layer = new_layer
        
        # Sütunları ComboBox'lara ekle
        fields = self.vector_layer.fields()
        field_names = [field.name() for field in fields]
        
        self.ilColumnComboBox.clear()
        self.ilceColumnComboBox.clear()
        self.ilColumnComboBox.addItems(field_names)
        self.ilceColumnComboBox.addItems(field_names)
        
        # Varsayılan sütunları seç
        il_index = self.ilColumnComboBox.findText("adm1_tr")
        ilce_index = self.ilceColumnComboBox.findText("adm2_tr")
        if il_index >= 0:
            self.ilColumnComboBox.setCurrentIndex(il_index)
        if ilce_index >= 0:
            self.ilceColumnComboBox.setCurrentIndex(ilce_index)
        
        # Sütun seçimi sinyallerini bağla
        self.ilColumnComboBox.currentTextChanged.connect(self.update_il_list)
        self.ilceColumnComboBox.currentTextChanged.connect(self.update_il_list)
        
        # İl seçimi değiştiğinde ilçe listesini güncelle
        self.ilComboBox.currentTextChanged.connect(self.update_ilce_combobox)
        
        # İl listesini güncelle
        self.update_il_list()
        
        # İlçe sınırları yüklendiğinde diğer grupları aktif hale getir
        self.earthquakeGroup.setEnabled(True)
        self.filterGroup.setEnabled(True)
        self.faultLinesGroup.setEnabled(True)
        self.settlementGroup.setEnabled(True)
        
        # Sütun seçme alanlarını aktif hale getir
        self.ilColumnComboBox.setEnabled(True)
        self.ilceColumnComboBox.setEnabled(True)
        self.ilColumnLabel.setEnabled(True)
        self.ilceColumnLabel.setEnabled(True)
        
        # Buffer alanını aktif hale getir
        self.bufferSpinBox.setEnabled(True)
        self.bufferLabel.setEnabled(True)
        
    def update_il_list(self):
        """Seçilen il sütununa göre il listesini güncelle"""
        if not self.ensure_valid_layer():
            return
            
        il_column = self.ilColumnComboBox.currentText()
        if not il_column:
            return
            
        il_list = []
        for feature in self.vector_layer.getFeatures():
            il = feature[il_column]
            if il and il not in il_list:
                il_list.append(il)
                
        il_list.sort()
        self.ilComboBox.clear()
        self.ilceComboBox.clear()
        self.ilComboBox.addItems(il_list)
        
    def update_ilce_combobox(self, selected_il):
        """İlçe listesini güncelle"""
        if not self.ensure_valid_layer():
            return
            
        # Önce fay hatlarını temizle
        self.clear_fault_lines()
        
        # Yerleşim noktalarını güncelle
        if self.settlement_layer:
            # İl değiştiğinde settlement layer'ı yeniden yükle
            if selected_il:
                self.update_settlement_filter()
                # İl değiştiğinde ekstra yenileme
                if self.iface and self.iface.mapCanvas():
                    self.iface.mapCanvas().refreshAllLayers()
                    QtCore.QTimer.singleShot(200, lambda: self.iface.mapCanvas().refresh())
            
        self.ilceComboBox.blockSignals(True)  # Sinyalleri geçici olarak durdur
        self.ilceComboBox.clear()
        self.ilceComboBox.addItem("")  # Boş seçenek
        
        if not selected_il:
            self.update_layer_name()
            self.vector_layer.setSubsetString("")
            self.zoom_to_layer()
            if self.earthquake_data is not None:
                self.apply_earthquake_filter()
            self.ilceComboBox.blockSignals(False)
            return
            
        il_column = self.ilColumnComboBox.currentText()
        ilce_column = self.ilceColumnComboBox.currentText()
        
        if not il_column or not ilce_column:
            self.ilceComboBox.blockSignals(False)
            return
            
        # Veritabanı sorgusu optimize edilmiş şekilde
        expression = f"\"{il_column}\" = '{selected_il}'"
        request = QgsFeatureRequest()
        request.setFilterExpression(expression)
        request.setFlags(QgsFeatureRequest.NoGeometry)
        request.setSubsetOfAttributes([ilce_column], self.vector_layer.fields())
        
        # Set kullanarak tekrarlayan değerleri otomatik filtrele
        ilce_set = {feature[ilce_column] for feature in self.vector_layer.getFeatures(request) 
                   if feature[ilce_column] and feature[ilce_column].strip()}
        
        # Set'ten listeye çevir ve sırala
        ilce_list = sorted(list(ilce_set))
        self.ilceComboBox.addItems(ilce_list)
        
        # Filtreyi uygula ve diğer güncellemeleri yap
        self.vector_layer.setSubsetString(expression)
        self.update_layer_name()
        self.zoom_to_layer()
        
        # UI'nin yanıt vermesini sağla
        QtWidgets.QApplication.processEvents()
        
        # Fay hatlarını gecikmeli olarak güncelle
        QTimer.singleShot(100, self.update_fault_lines)
        
        # Deprem verilerini güncelle
        if self.earthquake_data is not None:
            self.apply_earthquake_filter()
        
        self.ilceComboBox.blockSignals(False)  # Sinyalleri tekrar aç

    def update_layer_name(self, *args):
        if not self.ensure_valid_layer():
            return
            
        il = self.ilComboBox.currentText()
        ilce = self.ilceComboBox.currentText()
        buffer_distance = self.bufferSpinBox.value()
        
        # Ana katman için beyaza yakın, saydam stil oluştur
        main_symbol = QgsFillSymbol.createSimple({
            'color': '255,255,255,50',  # Beyaz renk, %80 saydamlık
            'style': 'solid',
            'outline_style': 'solid',
            'outline_width': '0.8',  # Çizgi kalınlığını artır
            'outline_color': '64,64,64,255'  # Daha koyu gri ve tam opak kenar çizgisi
        })
        
        # Ana katmanın stilini ayarla
        self.vector_layer.renderer().setSymbol(main_symbol)
        
        if il and ilce:
            # İl ve ilçe adlarını İngilizce formata çevir
            il_eng = self.normalize_text(il).lower()
            ilce_eng = self.normalize_text(ilce).lower()
            self.vector_layer.setName(f"{il_eng}_{ilce_eng}")  # province_district formatında
            filter_exp = self.get_filter_expression()
            self.vector_layer.setSubsetString(filter_exp)
            self.setup_layer_labeling(il, ilce)
            self.apply_buffer_style(buffer_distance)
            
            # Buffer alanını da kapsayacak şekilde zoom yap
            if self.buffer_layer and self.buffer_layer.isValid():
                combined_extent = self.buffer_layer.extent()
                combined_extent.combineExtentWith(self.vector_layer.extent())
                if self.iface and self.iface.mapCanvas():
                    combined_extent.scale(1.1)  # %10 daha geniş görünüm
                    self.iface.mapCanvas().setExtent(combined_extent)
                    self.iface.mapCanvas().refresh()
            else:
                self.zoom_to_layer()
                
        elif il:
            # Sadece il adını İngilizce formata çevir
            il_eng = self.normalize_text(il).lower()
            self.vector_layer.setName(il_eng)  # Sadece province ismi
            filter_exp = self.get_filter_expression()
            self.vector_layer.setSubsetString(filter_exp)
            self.setup_layer_labeling(il, None)
            self.apply_buffer_style(buffer_distance)
            
            # Buffer alanını da kapsayacak şekilde zoom yap
            if self.buffer_layer and self.buffer_layer.isValid():
                combined_extent = self.buffer_layer.extent()
                combined_extent.combineExtentWith(self.vector_layer.extent())
                if self.iface and self.iface.mapCanvas():
                    combined_extent.scale(1.1)  # %10 daha geniş görünüm
                    self.iface.mapCanvas().setExtent(combined_extent)
                    self.iface.mapCanvas().refresh()
            else:
                self.zoom_to_layer()
                
        else:
            self.vector_layer.setName(self.original_layer_name)  # Shapefile ismi
            self.vector_layer.setSubsetString("")  # Filtreyi temizle
            self.setup_layer_labeling(None, None)
            self.apply_buffer_style(0)  # Buffer'ı kaldır
            self.zoom_to_layer()
            
        # Ana katmanı yenile
        self.vector_layer.triggerRepaint()
        
    def setup_layer_labeling(self, il, ilce):
        """Katman etiketlemesini ayarla"""
        if not self.vector_layer:
            return
            
        # Eğer checkbox işaretli değilse etiketleri kapat
        if not self.showLabelsCheckBox.isChecked():
            self.vector_layer.setLabelsEnabled(False)
            self.vector_layer.triggerRepaint()
            return
            
        label_settings = QgsPalLayerSettings()
        text_format = QgsTextFormat()
        
        # Temel metin formatını ayarla
        text_format.setSize(8)  # Font boyutunu küçült
        text_format.setColor(QColor(0, 51, 102))  # Koyu lacivert renk
        text_format.setFont(QFont("Arial", weight=QFont.Bold))  # Kalın font
        
        # Buffer ayarlarını geliştir
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1.2)  # Buffer boyutunu artır
        buffer_settings.setColor(QColor(255, 255, 255, 240))  # Daha opak beyaz
        text_format.setBuffer(buffer_settings)
        
        label_settings.setFormat(text_format)
        label_settings.fieldName = "adm2_tr"  # İlçe ismi sütunu
        
        # Etiket yerleşim ayarlarını güncelle - merkeze sabitle
        label_settings.placement = QgsPalLayerSettings.OverPoint  # Nokta üzerine yerleşim
        label_settings.centroidWhole = True  # Tüm poligonu dikkate alarak merkez hesapla
        label_settings.centroidInside = True  # Merkez noktayı poligon içinde tut
        label_settings.dist = 0  # Merkez noktadan uzaklık sıfır olsun
        
        # Etiketlerin her zaman görünmesi için ayarlar
        label_settings.displayAll = True  # Tüm etiketleri göster
        label_settings.obstacle = False  # Çakışma kontrolünü kapat
        label_settings.priority = 10  # Yüksek öncelik
        
        # Eğer il seçili değilse veya sadece il seçiliyse daha büyük font kullan
        if not il or (il and not ilce):
            text_format.setSize(10)  # İl için biraz daha büyük font
            label_settings.setFormat(text_format)
            
        layer_settings = QgsVectorLayerSimpleLabeling(label_settings)
        self.vector_layer.setLabeling(layer_settings)
        self.vector_layer.setLabelsEnabled(True)
        self.vector_layer.triggerRepaint()

    def select_csv_file(self):
        """Deprem verilerini içeren CSV dosyasını seç"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Deprem CSV Dosyası Seç",
            "",
            "CSV Dosyası (*.csv)"
        )
        
        if file_path and os.path.exists(file_path):
            self.csv_file_path = file_path
            self.csvFileEdit.setText(file_path)
            self.load_earthquake_data(file_path)
            # Deprem verileri yüklendiğinde spinbox durumunu güncelle
            self.update_settlement_distance_spinbox()
            
    def load_earthquake_data(self, file_path):
        """CSV dosyasından deprem verilerini yükle"""
        try:
            # CSV'yi daha hızlı okumak için gerekli sütunları belirt
            required_columns = ['eventId', 'eventDate', 'longitude', 'latitude', 'depth', 'magnitudeType', 'magnitude', 'area']
            
            # CSV'yi oku ve tarih sütununu parse et
            self.earthquake_data = pd.read_csv(file_path, usecols=required_columns)
            
            # Tarih sütununu datetime'a çevir
            self.earthquake_data['eventDate'] = pd.to_datetime(self.earthquake_data['eventDate'], format='%Y-%m-%dT%H:%M:%S')
            
            # Geçersiz koordinatları filtrele
            mask = (
                self.earthquake_data['longitude'].between(-180, 180) &
                self.earthquake_data['latitude'].between(-90, 90) &
                self.earthquake_data['longitude'].notna() &
                self.earthquake_data['latitude'].notna()
            )
            self.earthquake_data = self.earthquake_data[mask]
            
            if len(self.earthquake_data) > 0:
                # Koordinatları numpy array'e dönüştür (daha hızlı işlem için)
                self.earthquake_points = np.column_stack((
                    self.earthquake_data['longitude'].values,
                    self.earthquake_data['latitude'].values
                ))
                
                # Yıl listesini güncelle
                self.update_year_list()
                
                # Yakınlık mesafesi ve yıl filtresi alanlarını aktif hale getir
                self.bufferSpinBox.setEnabled(True)
                self.bufferLabel.setEnabled(True)
                self.yearComboBox.setEnabled(True)
                self.endYearComboBox.setEnabled(True)
                self.yearRangeLabel.setEnabled(True)
                
                # Büyüklük filtresi alanlarını aktif hale getir
                self.minMagnitudeSpinBox.setEnabled(True)
                self.maxMagnitudeSpinBox.setEnabled(True)
                self.magnitudeRangeLabel.setEnabled(True)
                self.magnitudeSeparatorLabel.setEnabled(True)
                
                # Büyüklük aralığı değişikliklerini bağla
                self.minMagnitudeSpinBox.valueChanged.connect(self.on_magnitude_changed)
                self.maxMagnitudeSpinBox.valueChanged.connect(self.on_magnitude_changed)
                
                # Yerleşim noktası mesafesi spinbox durumunu güncelle
                self.update_settlement_distance_spinbox()
                
                # Başarılı mesajı göster
                QtWidgets.QMessageBox.information(
                    self,
                    "Başarılı",
                    f"CSV dosyası başarıyla yüklendi. Toplam {len(self.earthquake_data)} deprem verisi bulundu.",
                    QtWidgets.QMessageBox.Ok
                )
            else:
                self.earthquake_data = None
                self.earthquake_points = None
                # Tüm filtre alanlarını devre dışı bırak
                self.disable_filter_fields()
            
        except Exception as e:
            self.earthquake_data = None
            self.earthquake_points = None
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                f"CSV dosyası yüklenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )
        
    def update_year_list(self):
        """Deprem verilerinden yıl listesini güncelle"""
        if self.earthquake_data is not None:
            # Yılları al ve sırala
            years = sorted(self.earthquake_data['eventDate'].dt.year.unique())
            
            # ComboBox'ları temizle
            self.yearComboBox.clear()
            self.endYearComboBox.clear()
            
            # En küçük yılı başlangıç olarak seç
            min_year = str(min(years))
            
            # Başlangıç yılı için yılları ekle
            for year in years:
                self.yearComboBox.addItem(str(year))
            
            # Varsayılan başlangıç yılını ayarla ve bitiş yılını güncelle
            self.yearComboBox.setCurrentText(min_year)
            # Bu çağrı on_year_changed'i tetikleyecek ve bitiş yılını otomatik dolduracak

    def on_year_changed(self, selected_year):
        """Yıl seçimi değiştiğinde çağrılır"""
        if self.earthquake_data is not None:
            start_year = self.yearComboBox.currentText()
            
            # Başlangıç yılı değiştiğinde bitiş yılı seçeneklerini güncelle
            if self.sender() == self.yearComboBox:
                self.endYearComboBox.clear()
                start_year = int(start_year)
                years = sorted(self.earthquake_data['eventDate'].dt.year.unique())
                
                # Sadece başlangıç yılı ve sonrasını ekle
                available_years = [str(year) for year in years if year >= start_year]
                self.endYearComboBox.addItems(available_years)
                
                # Bitiş yılını mevcut yıllardan en büyük olanı yap
                self.endYearComboBox.setCurrentText(max(available_years))
            
            # Yıl kontrolü yap
            end_year = self.endYearComboBox.currentText()
            if start_year and end_year:
                start_year = int(start_year)
                end_year = int(end_year)
                
                if end_year < start_year:
                    # Bitiş yılını başlangıç yılı yap
                    self.endYearComboBox.setCurrentText(str(start_year))
            
            self.apply_earthquake_filter()

    def get_filter_expression(self):
        """Filtre ifadesini oluştur"""
        il = self.ilComboBox.currentText()
        ilce = self.ilceComboBox.currentText()
        il_column = self.ilColumnComboBox.currentText()
        ilce_column = self.ilceColumnComboBox.currentText()
        
        filter_exp = ""
        if il and ilce:
            filter_exp = f"\"{il_column}\" = '{il}' AND \"{ilce_column}\" = '{ilce}'"
        elif il:
            filter_exp = f"\"{il_column}\" = '{il}'"
            
        return filter_exp
        
    def get_filtered_earthquake_data(self):
        """Seçilen il, ilçe, yıl ve büyüklük aralığına göre deprem verilerini filtrele"""
        if self.earthquake_data is None or self.earthquake_points is None:
            return None
        
        if self.vector_layer is None:
            return None
            
        # Yerleşim noktası mesafesi kontrolü
        settlement_distance = self.settlementDistanceSpinBox.value()
        if settlement_distance > 0 and (not self.settlement_layer or not self.settlement_layer.isValid()):
            QtWidgets.QMessageBox.warning(
                self,
                "Uyarı",
                "Yerleşim noktalarına göre filtreleme yapabilmek için yerleşim noktası verilerinin yüklü olması gerekiyor.",
                QtWidgets.QMessageBox.Ok
            )
            self.settlementDistanceSpinBox.setValue(0)
            return None
            
        il = self.ilComboBox.currentText()
        ilce = self.ilceComboBox.currentText()
        buffer_distance_km = self.bufferSpinBox.value()
        filter_exp = self.get_filter_expression()
        
        # Yıl filtresi parametrelerini al
        start_year = self.yearComboBox.currentText()
        end_year = self.endYearComboBox.currentText()
        
        # Büyüklük filtresi parametrelerini al
        min_magnitude = self.minMagnitudeSpinBox.value()
        max_magnitude = self.maxMagnitudeSpinBox.value()
        
        # Cache kontrolü - Aynı parametrelerle tekrar hesaplama yapılmasını önler
        cache_params = (il, ilce, buffer_distance_km, filter_exp, start_year, end_year, 
                       min_magnitude, max_magnitude, settlement_distance)
        if (hasattr(self, 'cached_result') and 
            hasattr(self, 'cached_params') and 
            self.cached_params == cache_params):
            return self.cached_result
            
        if not filter_exp:
            return None
            
        try:
            # Önce yıl ve büyüklük filtresini uygula (daha az veri üzerinde işlem yapmak için)
            filtered_data = self.earthquake_data
            
            # Yıl filtresi - numpy ile hızlı filtreleme
            if start_year and end_year:
                years = filtered_data['eventDate'].dt.year.values
                year_mask = (years >= int(start_year)) & (years <= int(end_year))
                filtered_data = filtered_data[year_mask]
            
            # Büyüklük filtresi - numpy ile hızlı filtreleme
            magnitude_mask = (filtered_data['magnitude'].values >= min_magnitude) & (filtered_data['magnitude'].values <= max_magnitude)
            filtered_data = filtered_data[magnitude_mask]
            
            if filtered_data.empty:
                return None
            
            # Geometri işlemleri için optimize edilmiş kod
            request = QgsFeatureRequest().setFilterExpression(filter_exp)
            features = list(self.vector_layer.getFeatures(request))
            if not features:
                return None
                
            # Geometrileri tek seferde birleştir
            geometries = [f.geometry() for f in features]
            selected_geometry = QgsGeometry.unaryUnion(geometries)
            
            if not selected_geometry or selected_geometry.isEmpty():
                return None

            # Koordinat dönüşümleri için transform nesnelerini bir kez oluştur
            wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
            utm_crs = QgsCoordinateReferenceSystem('EPSG:32636')
            transform_to_wgs84 = QgsCoordinateTransform(self.vector_layer.crs(), wgs84, QgsProject.instance())
            transform_to_utm = QgsCoordinateTransform(wgs84, utm_crs, QgsProject.instance())
            transform_back_to_wgs84 = QgsCoordinateTransform(utm_crs, wgs84, QgsProject.instance())

            try:
                # Geometriyi WGS84'e dönüştür
                selected_geometry.transform(transform_to_wgs84)

                # Buffer işlemi
                if buffer_distance_km > 0:
                    selected_geometry.transform(transform_to_utm)
                    selected_geometry = selected_geometry.buffer(buffer_distance_km * 1000, 5)
                    selected_geometry.transform(transform_back_to_wgs84)

                # Yerleşim noktalarına göre filtreleme
                if self.settlement_layer and self.settlement_layer.isValid() and settlement_distance > 0:
                    settlement_features = list(self.settlement_layer.getFeatures())
                    if settlement_features:
                        # Yerleşim noktalarını birleştir ve buffer uygula
                        settlement_geometries = []
                        for f in settlement_features:
                            geom = f.geometry()
                            if geom and not geom.isEmpty() and geom.isGeosValid():
                                # Geometriyi WGS84'e dönüştür
                                geom_wgs84 = QgsGeometry(geom)
                                if self.settlement_layer.crs() != wgs84:
                                    transform_to_wgs84_settlement = QgsCoordinateTransform(
                                        self.settlement_layer.crs(), 
                                        wgs84, 
                                        QgsProject.instance()
                                    )
                                    geom_wgs84.transform(transform_to_wgs84_settlement)
                                settlement_geometries.append(geom_wgs84)
                        
                        if not settlement_geometries:
                            return None
                            
                        settlement_geometry = QgsGeometry.unaryUnion(settlement_geometries)
                        if not settlement_geometry or settlement_geometry.isEmpty():
                            return None
                        
                        try:
                            # UTM'e dönüştür ve buffer uygula
                            settlement_geometry.transform(transform_to_utm)
                            settlement_geometry = settlement_geometry.buffer(settlement_distance * 1000, 5)
                            settlement_geometry.transform(transform_back_to_wgs84)
                            
                            # Seçili alan ile kesişimi al
                            selected_geometry = selected_geometry.intersection(settlement_geometry)
                            
                            if not selected_geometry or selected_geometry.isEmpty():
                                return None
                        except Exception as e:
                            QtWidgets.QMessageBox.warning(
                                self,
                                "Uyarı",
                                "Yerleşim noktaları filtrelemesi sırasında hata oluştu. Lütfen farklı bir mesafe değeri deneyin.",
                                QtWidgets.QMessageBox.Ok
                            )
                            return None

            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Uyarı",
                    "Koordinat dönüşümü sırasında hata oluştu. Lütfen farklı bir alan seçin.",
                    QtWidgets.QMessageBox.Ok
                )
                return None

            # Numpy ile vektörize edilmiş işlemler
            bbox = selected_geometry.boundingBox()
            points = np.column_stack((
                filtered_data['longitude'].values,
                filtered_data['latitude'].values
            ))
            
            # Geçersiz koordinatları filtrele
            valid_coords_mask = np.all(np.isfinite(points), axis=1)
            points = points[valid_coords_mask]
            if len(points) == 0:
                return None
                
            filtered_data = filtered_data[valid_coords_mask]
            
            # Tek bir numpy maskesi ile hızlı filtreleme
            bbox_mask = np.all([
                points[:, 0] >= bbox.xMinimum(),
                points[:, 0] <= bbox.xMaximum(),
                points[:, 1] >= bbox.yMinimum(),
                points[:, 1] <= bbox.yMaximum()
            ], axis=0)
            
            if not np.any(bbox_mask):
                return None
                
            # Sadece bbox içindeki noktaları al
            potential_points = points[bbox_mask]
            potential_indices = filtered_data.index[bbox_mask]
            
            if len(potential_points) == 0:
                return None
                
            # Geometri kontrolünü optimize et - toplu işlem
            point_geometries = [QgsGeometry.fromPointXY(QgsPointXY(x, y)) for x, y in potential_points]
            geometry_mask = np.array([selected_geometry.contains(point) for point in point_geometries])
            
            # Numpy ile hızlı filtreleme
            final_indices = potential_indices[geometry_mask]
            if len(final_indices) == 0:
                return None
                
            # Pandas ile verimli veri filtreleme
            final_data = filtered_data.loc[final_indices].copy()
            
            # Sonucu cache'le
            self.cached_result = final_data if not final_data.empty else None
            self.cached_params = cache_params
            
            return self.cached_result
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                None,
                "Hata",
                f"Deprem verileri filtrelenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )
            return None

    def select_xlsx_file(self):
        """Nüfus verilerini içeren Excel dosyasını seç"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Nüfus Excel Dosyası Seç",
            "",
            "Excel Dosyası (*.xlsx)"
        )
        
        if file_path and os.path.exists(file_path):
            self.xlsx_file_path = file_path
            self.xlsxFileEdit.setText(file_path)
            self.load_population_data(file_path)

    def load_population_data(self, file_path):
        """Excel dosyasından nüfus verilerini yükle"""
        try:
            # Excel dosyasını 9. satırdan başlayarak oku ve sütun isimlerini belirle
            column_names = [
                'İL KAYIT NO', 'İLÇE KAYIT NO', 'İL ADI', 'İLÇE ADI',
                'GENEL TOPLAM_TOPLAM', 'GENEL TOPLAM_ERKEK', 'GENEL TOPLAM_KADIN',
                'İL ve İLÇE MERKEZLERİ_TOPLAM', 'İL ve İLÇE MERKEZLERİ_ERKEK', 'İL ve İLÇE MERKEZLERİ_KADIN',
                'BELDE ve KÖYLER_TOPLAM', 'BELDE ve KÖYLER_ERKEK', 'BELDE ve KÖYLER_KADIN'
            ]
            
            df = pd.read_excel(
                file_path,
                sheet_name='İLÇE NÜFUSU',
                skiprows=8,
                names=column_names
            )
            
            # Sütun isimlerini kontrol et
            required_columns = [
                'İL KAYIT NO', 'İLÇE KAYIT NO', 'İL ADI', 'İLÇE ADI',
                'GENEL TOPLAM_TOPLAM', 'GENEL TOPLAM_ERKEK', 'GENEL TOPLAM_KADIN'
            ]
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Hata",
                    f"Excel dosyasında gerekli sütunlar eksik: {', '.join(missing_columns)}",
                    QtWidgets.QMessageBox.Ok
                )
                return
            
            # NaN değerleri temizle
            df = df.dropna(subset=['İL ADI', 'İLÇE ADI'])
            
            self.population_data = df
            
            QtWidgets.QMessageBox.information(
                self,
                "Başarılı",
                f"Nüfus verileri başarıyla yüklendi. Toplam {len(df)} kayıt bulundu.",
                QtWidgets.QMessageBox.Ok
            )
            
        except Exception as e:
            self.population_data = None
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                f"Excel dosyası yüklenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )

    def validate_and_accept(self):
        """İl seçimini kontrol et ve onayla"""
        if not self.file_path:
            QtWidgets.QMessageBox.warning(
                self,
                "Uyarı",
                "Lütfen ilçe sınırları shapefile seçiniz.",
                QtWidgets.QMessageBox.Ok
            )
            return
            
        if not self.ilComboBox.currentText():
            QtWidgets.QMessageBox.warning(
                self,
                "Uyarı",
                "Lütfen bir il seçiniz.",
                QtWidgets.QMessageBox.Ok
            )
            return
            
        self.accept()

    def disable_fields(self):
        """Tüm alanları devre dışı bırak"""
        # Deprem verileri grubu
        self.earthquakeGroup.setEnabled(False)
        
        # Bölge seçimi grubu
        self.filterGroup.setEnabled(False)
        
        # Diri fay hatları grubu
        self.faultLinesGroup.setEnabled(False)
        
        # Tamam butonu
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)
        
    def enable_fields(self):
        """Tüm alanları aktif hale getir"""
        # Deprem verileri grubu
        self.earthquakeGroup.setEnabled(True)
        
        # Bölge seçimi grubu
        self.filterGroup.setEnabled(True)
        
        # Diri fay hatları grubu
        self.faultLinesGroup.setEnabled(True)
        
        # İl seçildiğinde Tamam butonunu aktif et
        self.ilComboBox.currentTextChanged.connect(self.update_ok_button)
        
    def update_ok_button(self, selected_il):
        """İl seçimine göre Tamam butonunu güncelle"""
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(bool(selected_il))

    def apply_buffer_style(self, buffer_distance_km):
        """Katmana buffer stilini uygula"""
        # Eski buffer katmanını temizle
        if self.buffer_layer:
            QgsProject.instance().removeMapLayer(self.buffer_layer.id())
            self.buffer_layer = None

        if not self.vector_layer or buffer_distance_km <= 0:
            return

        # Buffer layer ismi için il ve ilçe bilgisini al
        il = self.ilComboBox.currentText()
        ilce = self.ilceComboBox.currentText()
        
        # İl ve ilçe adlarını İngilizce formata çevir ve buffer ismini oluştur
        il_eng = self.normalize_text(il).lower() if il else ""
        ilce_eng = self.normalize_text(ilce).lower() if ilce else ""
        buffer_name = f"{il_eng}_{ilce_eng}_buffer" if ilce else f"{il_eng}_buffer"

        # Memory layer'ı yeni isimle oluştur
        buffer_layer = QgsVectorLayer(
            "Polygon?crs=" + self.vector_layer.crs().authid(), 
            buffer_name, 
            "memory"
        )

        # Geometriyi projeksiyon koordinat sistemine dönüştür
        utm_crs = QgsCoordinateReferenceSystem('EPSG:32636')  # UTM zone 36N
        transform_to_utm = QgsCoordinateTransform(self.vector_layer.crs(), utm_crs, QgsProject.instance())
        
        # Seçili özelliklerin geometrilerini al ve birleştir
        features = list(self.vector_layer.getFeatures())
        if not features:
            return

        combined_geometry = features[0].geometry()
        for feature in features[1:]:
            combined_geometry = combined_geometry.combine(feature.geometry())

        # Geometriyi UTM'e dönüştür
        utm_geometry = combined_geometry
        utm_geometry.transform(transform_to_utm)

        # Buffer uygula
        buffer_distance_m = buffer_distance_km * 1000
        buffer_geometry = utm_geometry.buffer(buffer_distance_m, 5)

        # Geri orijinal CRS'e dönüştür
        transform_back = QgsCoordinateTransform(utm_crs, self.vector_layer.crs(), QgsProject.instance())
        buffer_geometry.transform(transform_back)

        # Buffer için sembol oluştur - beyaza yakın, saydam stil
        buffer_symbol = QgsFillSymbol.createSimple({
            'color': '255,255,255,30',  # Beyaz renk, %88 saydamlık
            'style': 'solid',
            'outline_style': 'dash',  # Kesikli çizgi
            'outline_width': '0.5',  # İnce çizgi
            'outline_color': '64,64,64,200'  # Koyu gri, yarı saydam kenar çizgisi
        })

        # Yeni bir memory layer oluştur ve buffer geometrisini ekle
        buffer_provider = buffer_layer.dataProvider()
        buffer_feature = QgsFeature()
        buffer_feature.setGeometry(buffer_geometry)
        buffer_provider.addFeatures([buffer_feature])

        # Buffer katmanını haritaya ekle
        QgsProject.instance().addMapLayer(buffer_layer)
        buffer_layer.setRenderer(QgsSingleSymbolRenderer(buffer_symbol))
        
        # Ölçek bağımlı görünürlük ayarla
        buffer_layer.setScaleBasedVisibility(True)
        buffer_layer.setMinimumScale(5000000)  
        buffer_layer.setMaximumScale(50000)  

        self.buffer_layer = buffer_layer  # Buffer layer referansını sakla

        # Buffer katmanını ana katmanın altına yerleştir
        root = QgsProject.instance().layerTreeRoot()
        buffer_node = root.findLayer(buffer_layer.id())
        main_node = root.findLayer(self.vector_layer.id())
        if buffer_node and main_node:
            clone = buffer_node.clone()
            parent = main_node.parent()
            parent.insertChildNode(parent.children().index(main_node) + 1, clone)
            root.removeChildNode(buffer_node)

        # Sadece buffer katmanını yenile
        buffer_layer.triggerRepaint()

    def apply_earthquake_filter(self):
        """Deprem verilerini filtrele ve göster"""
        try:
            # Cache'i temizle
            if hasattr(self, 'cached_result'):
                delattr(self, 'cached_result')
            if hasattr(self, 'cached_params'):
                delattr(self, 'cached_params')
            
            # Önce mevcut deprem katmanlarını temizle
            for layer in QgsProject.instance().mapLayersByName("Depremler"):
                QgsProject.instance().removeMapLayer(layer.id())
            
            # Yeni filtrelenmiş verileri al
            filtered_data = self.get_filtered_earthquake_data()
            
            # UI'nin yanıt vermesini sağla
            QtWidgets.QApplication.processEvents()
            
            # Filtrelenmiş verileri sinyal ile gönder
            self.earthquakeDataFiltered.emit(filtered_data)
            
            return filtered_data
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                None,
                "Hata",
                f"Deprem filtreleme sırasında hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )
            return None

    def on_ilce_changed(self, selected_ilce):
        """İlçe değiştiğinde çağrılır"""
        # Mevcut işlemleri yap
        self.update_layer_name()
        self.update_fault_lines()
        
        # Yerleşim noktalarını güncelle
        if self.settlement_layer:
            self.update_settlement_filter()
        
        # Deprem verilerini güncelle
        if self.earthquake_data is not None:
            self.apply_earthquake_filter()

    def on_buffer_changed(self, value):
        """Buffer değeri değiştiğinde çağrılır"""
        # UI'nin yanıt vermesini sağla
        QtWidgets.QApplication.processEvents()
        
        # Önce layer ismini ve buffer stilini güncelle
        self.update_layer_name()
        
        # Fay hatlarını temizle ve güncelle
        self.clear_fault_lines()
        QTimer.singleShot(100, self.update_fault_lines)
        
        # Deprem verilerini yeniden filtrele
        if self.earthquake_data is not None:
            self.apply_earthquake_filter()

    def create_earthquake_layer(self, earthquake_data):
        """Bu fonksiyon artık kullanılmıyor - Plugin sınıfına taşındı"""
        pass

    def style_earthquake_layer(self, layer):
        """Bu fonksiyon artık kullanılmıyor - Plugin sınıfına taşındı"""
        pass

    def disable_filter_fields(self):
        """Filtre alanlarını devre dışı bırak"""
        self.bufferSpinBox.setEnabled(False)
        self.bufferLabel.setEnabled(False)
        self.yearComboBox.setEnabled(False)
        self.endYearComboBox.setEnabled(False)
        self.yearRangeLabel.setEnabled(False)
        self.minMagnitudeSpinBox.setEnabled(False)
        self.maxMagnitudeSpinBox.setEnabled(False)
        self.magnitudeRangeLabel.setEnabled(False)
        self.magnitudeSeparatorLabel.setEnabled(False)

    def on_magnitude_changed(self, value):
        """Büyüklük aralığı değiştiğinde çağrılır"""
        min_mag = self.minMagnitudeSpinBox.value()
        max_mag = self.maxMagnitudeSpinBox.value()
        
        # Minimum büyüklük maksimumdan büyükse, maksimumu minimuma eşitle
        if min_mag > max_mag:
            if self.sender() == self.minMagnitudeSpinBox:
                self.maxMagnitudeSpinBox.setValue(min_mag)
            else:
                self.minMagnitudeSpinBox.setValue(max_mag)
        
        # Deprem verilerini filtrele
        self.apply_earthquake_filter()

    def select_fault_line_file(self):
        """Diri fay hatları shapefile'ını seç"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Diri Fay Hatları Shapefile Seç",
            "",
            "Shapefile (*.shp)"
        )
        
        if file_path and os.path.exists(file_path):
            self.fault_line_layer = self.load_fault_line_layer(file_path)
            if self.fault_line_layer:
                self.faultLineFileEdit.setText(file_path)
                self.update_fault_lines()

    def load_fault_line_layer(self, file_path):
        """Diri fay hatları layer'ını yükle"""
        try:
            # Önce mevcut katmanı temizle
            if self.fault_line_layer and self.fault_line_layer.id() in QgsProject.instance().mapLayers():
                QgsProject.instance().removeMapLayer(self.fault_line_layer.id())
            
            # Yeni katmanı yükle
            layer = QgsVectorLayer(file_path, "Diri Fay Hatları", "ogr")
            if not layer.isValid():
                QtWidgets.QMessageBox.critical(
                    self,
                    "Hata",
                    "Diri fay hatları shapefile yüklenemedi!",
                    QtWidgets.QMessageBox.Ok
                )
                return None

            # Koordinat sistemini kontrol et ve dönüştür
            if layer.crs() != self.target_crs:
                # Memory layer oluştur
                uri = f"LineString?crs={self.target_crs.authid()}"
                memory_layer = QgsVectorLayer(uri, "Diri Fay Hatları", "memory")
                
                # Alan özelliklerini kopyala
                provider = memory_layer.dataProvider()
                attrs = layer.fields()
                provider.addAttributes(attrs)
                memory_layer.updateFields()
                
                # Dönüşüm için transform oluştur
                transform = QgsCoordinateTransform(
                    layer.crs(),
                    self.target_crs,
                    QgsProject.instance()
                )
                
                # Özellikleri toplu olarak dönüştür ve ekle
                features = []
                total = layer.featureCount()
                for i, feature in enumerate(layer.getFeatures()):
                    if i % 1000 == 0:  # Her 1000 özellikte bir ilerleme göster
                        QtWidgets.QApplication.processEvents()  # UI'nin yanıt vermesini sağla
                        
                    new_feature = QgsFeature()
                    new_feature.setAttributes(feature.attributes())
                    geom = feature.geometry()
                    geom.transform(transform)
                    new_feature.setGeometry(geom)
                    features.append(new_feature)
                
                # Özellikleri toplu olarak ekle
                provider.addFeatures(features)
                memory_layer.updateExtents()
                layer = memory_layer

            # Stil ayarla
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(self.fault_line_color)
            symbol.setWidth(0.5)
            layer.renderer().setSymbol(symbol)

            return layer
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                f"Fay hatları yüklenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )
            return None

    def clear_fault_lines(self):
        """Mevcut fay hatlarını temizle"""
        if self.fault_line_layer and self.fault_line_layer.id() in QgsProject.instance().mapLayers():
            QgsProject.instance().removeMapLayer(self.fault_line_layer.id())
            self.fault_line_layer = None
            if self.iface and self.iface.mapCanvas():
                self.iface.mapCanvas().refresh()

    def update_fault_lines(self):
        """Seçili il, ilçe ve buffer mesafesine göre fay hatlarını güncelle"""
        try:
            # Önce mevcut fay hatlarını temizle
            self.clear_fault_lines()
            
            # Aynı isimli diğer katmanları da temizle
            for layer in QgsProject.instance().mapLayers().values():
                if layer.name().endswith('_diri_faylar'):
                    QgsProject.instance().removeMapLayer(layer.id())
            
            # Katmanların geçerliliğini kontrol et
            if not self.vector_layer or not self.vector_layer.isValid():
                return
                
            if not hasattr(self, 'original_fault_layer') or not self.original_fault_layer or not self.original_fault_layer.isValid():
                # Orijinal fay hattı layer'ını sakla
                self.original_fault_layer = self.fault_line_layer
                
            if not self.original_fault_layer or not self.original_fault_layer.isValid():
                return
                
            # Seçili alanın geometrisini al
            filter_exp = self.get_filter_expression()
            if not filter_exp:
                return

            # İl ve ilçe adlarını al
            il = self.ilComboBox.currentText()
            ilce = self.ilceComboBox.currentText()
            
            # Layer ismi için il ve ilçe adlarını düzenle
            il_eng = self.normalize_text(il).lower() if il else ""
            ilce_eng = self.normalize_text(ilce).lower() if ilce else ""
            layer_name = f"{il_eng}_{ilce_eng}_diri_faylar" if ilce else f"{il_eng}_diri_faylar"

            # Seçili alanın geometrisini al - optimize edilmiş şekilde
            request = QgsFeatureRequest().setFilterExpression(filter_exp)
            features = list(self.vector_layer.getFeatures(request))
            if not features:
                return

            # Seçili alanın geometrilerini birleştir
            selected_geometry = QgsGeometry.unaryUnion([f.geometry() for f in features])
            if not selected_geometry or selected_geometry.isEmpty():
                return

            # Buffer mesafesini uygula
            buffer_distance = self.bufferSpinBox.value()
            if buffer_distance > 0:
                # UTM koordinat sistemine dönüştür
                utm_crs = QgsCoordinateReferenceSystem('EPSG:32636')
                transform_to_utm = QgsCoordinateTransform(self.vector_layer.crs(), utm_crs, QgsProject.instance())
                transform_back = QgsCoordinateTransform(utm_crs, self.vector_layer.crs(), QgsProject.instance())

                # Geometriyi UTM'e dönüştür
                selected_geometry.transform(transform_to_utm)
                # Buffer uygula
                selected_geometry = selected_geometry.buffer(buffer_distance * 1000, 5)
                # Geri dönüştür
                selected_geometry.transform(transform_back)

            # Yeni memory layer oluştur
            uri = f"LineString?crs={self.target_crs.authid()}"
            filtered_layer = QgsVectorLayer(uri, layer_name, "memory")
            
            if not filtered_layer.isValid():
                raise Exception("Filtrelenmiş fay hatları katmanı oluşturulamadı")
            
            # Alan özelliklerini kopyala
            provider = filtered_layer.dataProvider()
            provider.addAttributes(self.original_fault_layer.fields())
            filtered_layer.updateFields()

            # Koordinat dönüşümü için transform nesnelerini oluştur
            fault_to_target = QgsCoordinateTransform(
                self.original_fault_layer.crs(),
                self.target_crs,
                QgsProject.instance()
            )

            # Önce boundingBox ile kabaca filtrele
            bbox = selected_geometry.boundingBox()
            request = QgsFeatureRequest().setFilterRect(bbox)
            
            features_to_add = []
            for feature in self.original_fault_layer.getFeatures(request):
                # Fay hattı geometrisini al ve dönüştür
                fault_geom = feature.geometry()
                if fault_geom and not fault_geom.isEmpty():
                    # Geometriyi hedef koordinat sistemine dönüştür
                    fault_geom.transform(fault_to_target)
                    
                    # Seçili alan ile kesişimi kontrol et
                    if fault_geom.intersects(selected_geometry):
                        # Kesişen kısmı al
                        clipped_geom = fault_geom.intersection(selected_geometry)
                        if not clipped_geom.isEmpty():
                            new_feature = QgsFeature(feature)
                            new_feature.setGeometry(clipped_geom)
                            features_to_add.append(new_feature)
                
                # Her 100 özellikte bir UI'nin yanıt vermesini sağla
                if len(features_to_add) % 100 == 0:
                    QtWidgets.QApplication.processEvents()

            # Kesişen özellikleri ekle
            if features_to_add:
                provider.addFeatures(features_to_add)
                filtered_layer.updateExtents()

                # Stil ayarla
                symbol = QgsSymbol.defaultSymbol(filtered_layer.geometryType())
                symbol.setColor(self.fault_line_color)
                symbol.setWidth(0.5)
                filtered_layer.renderer().setSymbol(symbol)

                # Yeni katmanı ekle
                QgsProject.instance().addMapLayer(filtered_layer, False)  # False ile layer tree'ye otomatik eklemeyi engelle
                
                # Layer tree'yi al ve fay hattı katmanını en üste ekle
                root = QgsProject.instance().layerTreeRoot()
                root.insertLayer(0, filtered_layer)  # 0 indeksi ile en üste ekle
                
                self.fault_line_layer = filtered_layer
                
                # Katmanı yenile
                if self.iface and self.iface.mapCanvas():
                    self.iface.mapCanvas().refresh()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                f"Fay hatları güncellenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )

    def select_settlement_file(self):
        """Yerleşim noktaları shapefile'ını seç"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Yerleşim Noktaları Shapefile Seç",
            "",
            "Shapefile (*.shp)"
        )
        
        if file_path and os.path.exists(file_path):
            self.settlement_file_path = file_path
            self.settlementFileEdit.setText(file_path)
            self.load_settlement_layer(file_path)
            
    def load_settlement_layer(self, file_path):
        """Yerleşim noktaları layer'ını yükle"""
        try:
            # Önce mevcut katmanı temizle
            if self.settlement_layer and self.settlement_layer.id() in QgsProject.instance().mapLayers():
                QgsProject.instance().removeMapLayer(self.settlement_layer.id())
            
            # Geçici source layer oluştur
            source_layer = QgsVectorLayer(file_path, "temp", "ogr")
            if not source_layer.isValid():
                raise Exception("Kaynak shapefile yüklenemedi")

            # Memory layer oluştur
            uri = f"Point?crs={self.target_crs.authid()}"
            memory_layer = QgsVectorLayer(uri, "yerlesim_noktalari", "memory")
            if not memory_layer.isValid():
                raise Exception("Memory layer oluşturulamadı")

            # Alan özelliklerini kopyala
            provider = memory_layer.dataProvider()
            attrs = source_layer.fields()
            provider.addAttributes(attrs)
            memory_layer.updateFields()

            # Dönüşüm için transform oluştur
            transform = QgsCoordinateTransform(
                source_layer.crs(),
                self.target_crs,
                QgsProject.instance()
            )

            # Özellikleri toplu olarak dönüştür ve ekle
            features = []
            batch_size = 10000
            
            for feature in source_layer.getFeatures():
                new_feature = QgsFeature(memory_layer.fields())
                new_feature.setAttributes(feature.attributes())
                geom = feature.geometry()
                geom.transform(transform)
                new_feature.setGeometry(geom)
                features.append(new_feature)
                
                if len(features) >= batch_size:
                    provider.addFeatures(features)
                    features = []
                    # UI'nin yanıt vermesini sağla
                    QtWidgets.QApplication.processEvents()

            # Kalan özellikleri ekle
            if features:
                provider.addFeatures(features)

            memory_layer.updateExtents()
            
            # Spatial index oluştur
            memory_layer.dataProvider().createSpatialIndex()
            
            self.settlement_layer = memory_layer
            
            # Sütunları ComboBox'lara ekle
            fields = memory_layer.fields()
            field_names = [field.name() for field in fields]
            
            self.settlementIlColumnComboBox.clear()
            self.settlementIlceColumnComboBox.clear()
            self.settlementIlColumnComboBox.addItems(field_names)
            self.settlementIlceColumnComboBox.addItems(field_names)
            
            # Varsayılan sütunları seç
            il_index = self.settlementIlColumnComboBox.findText("Il_Adi")
            ilce_index = self.settlementIlceColumnComboBox.findText("Ilce_Adi")
            if il_index >= 0:
                self.settlementIlColumnComboBox.setCurrentIndex(il_index)
            if ilce_index >= 0:
                self.settlementIlceColumnComboBox.setCurrentIndex(ilce_index)
            
            # Alanları aktif hale getir
            self.settlementIlColumnComboBox.setEnabled(True)
            self.settlementIlceColumnComboBox.setEnabled(True)
            self.settlementIlLabel.setEnabled(True)
            self.settlementIlceLabel.setEnabled(True)
            
            # Yerleşim noktası mesafesi spinbox'ını aktif hale getir
            # Sadece deprem verileri de yüklüyse aktif olacak
            self.update_settlement_distance_spinbox()
            
            # İlk filtrelemeyi uygula
            self.update_settlement_filter()
            
            # Geçici layer'ı temizle
            del source_layer
            
        except Exception as e:
            self.settlement_layer = None
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                f"Yerleşim noktaları yüklenirken hata oluştu: {str(e)}",
                QtWidgets.QMessageBox.Ok
            )
            self.update_settlement_distance_spinbox()
            return None

    def update_settlement_filter(self):
        """Seçili il ve ilçeye göre yerleşim noktalarını filtrele"""
        if not self.settlement_layer or not self.vector_layer:
            return
            
        il = self.ilComboBox.currentText()
        ilce = self.ilceComboBox.currentText()
        
        # Layer ismini güncelle
        il_eng = self.normalize_text(il).lower() if il else ""
        ilce_eng = self.normalize_text(ilce).lower() if ilce else ""
        if il and ilce:
            layer_name = f"{il_eng}_{ilce_eng}_yerlesim_noktalari"
        elif il:
            layer_name = f"{il_eng}_yerlesim_noktalari"
        else:
            layer_name = "yerlesim_noktalari"
        
        # Aynı isimli diğer katmanları temizle
        for layer in QgsProject.instance().mapLayersByName(layer_name):
            if layer.id() != self.settlement_layer.id():
                QgsProject.instance().removeMapLayer(layer.id())
        
        # Tüm buffer katmanlarını temizle
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.name().endswith('_yerlesim_noktalari_buffer'):
                QgsProject.instance().removeMapLayer(layer.id())
        
        self.settlement_layer.setName(layer_name)
        
        if not il:
            self.settlement_layer.setSubsetString("")
            return
            
        # Filtre ifadesini oluştur
        il_column = self.settlementIlColumnComboBox.currentText()
        ilce_column = self.settlementIlceColumnComboBox.currentText()
        
        # Önce sadece il/ilçe bazlı filtreleme yap
        if ilce:
            filter_exp = f"(\"{il_column}\" = '{il}') AND (\"{ilce_column}\" = '{ilce}')"
        else:
            filter_exp = f"(\"{il_column}\" = '{il}')"
        
        # Filtreyi uygula
        self.settlement_layer.setSubsetString(filter_exp)
        
        # Yerleşim noktası mesafesi
        settlement_distance = self.settlementDistanceSpinBox.value()
        
        # Katmanı haritaya ekle (eğer eklenmemişse)
        if not QgsProject.instance().mapLayer(self.settlement_layer.id()):
            # Stil ayarla
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'circle',
                'color': '0,0,255,180',
                'size': '2',
                'outline_style': 'solid',
                'outline_width': '0.4',
                'outline_color': '0,0,128,255'
            })
            self.settlement_layer.renderer().setSymbol(symbol)
            
            # Ölçek bağımlı görünürlüğü kaldır
            self.settlement_layer.setScaleBasedVisibility(False)
            
            # Render ayarlarını optimize et
            self.settlement_layer.renderer().setForceRasterRender(False)
            
            # Katmanı ekle
            QgsProject.instance().addMapLayer(self.settlement_layer, False)
            
            # Layer tree'yi al ve yerleşim noktalarını fay hatlarının altına ekle
            root = QgsProject.instance().layerTreeRoot()
            root.insertLayer(1, self.settlement_layer)
        
        # Eğer yerleşim noktası mesafesi seçilmişse buffer katmanı oluştur
        if settlement_distance > 0:
            # Memory layer oluştur
            buffer_layer_name = layer_name + "_buffer"
            uri = f"Polygon?crs={self.target_crs.authid()}"
            buffer_layer = QgsVectorLayer(uri, buffer_layer_name, "memory")
            
            if not buffer_layer.isValid():
                return
                
            # Alan özelliklerini kopyala
            provider = buffer_layer.dataProvider()
            attrs = self.settlement_layer.fields()
            provider.addAttributes(attrs)
            buffer_layer.updateFields()
            
            # UTM koordinat sistemine dönüşüm için transform oluştur
            utm_crs = QgsCoordinateReferenceSystem('EPSG:32636')  # UTM zone 36N
            transform_to_utm = QgsCoordinateTransform(self.settlement_layer.crs(), utm_crs, QgsProject.instance())
            transform_back = QgsCoordinateTransform(utm_crs, self.settlement_layer.crs(), QgsProject.instance())
            
            # Her yerleşim noktası için buffer oluştur
            features = []
            for feature in self.settlement_layer.getFeatures():
                # Geometriyi UTM'e dönüştür
                geom = feature.geometry()
                geom.transform(transform_to_utm)
                
                # Buffer uygula (km'yi metreye çevir)
                buffer_geom = geom.buffer(settlement_distance * 1000, 25)  # 25 segment ile daha yuvarlak
                
                # Geri dönüştür
                buffer_geom.transform(transform_back)
                
                # Yeni özellik oluştur
                new_feature = QgsFeature(buffer_layer.fields())
                new_feature.setAttributes(feature.attributes())
                new_feature.setGeometry(buffer_geom)
                features.append(new_feature)
                
                # Her 100 özellikte bir UI'nin yanıt vermesini sağla
                if len(features) % 100 == 0:
                    QtWidgets.QApplication.processEvents()
            
            # Özellikleri toplu olarak ekle
            provider.addFeatures(features)
            buffer_layer.updateExtents()
            
            # Buffer stil ayarları
            symbol = QgsFillSymbol.createSimple({
                'color': '0,0,255,50',  # Açık mavi, %80 saydamlık
                'style': 'solid',
                'outline_style': 'dash',
                'outline_width': '0.4',
                'outline_color': '0,0,255,100'  # Mavi kenar, %61 saydamlık
            })
            buffer_layer.renderer().setSymbol(symbol)
            
            # Katmanı ekle
            QgsProject.instance().addMapLayer(buffer_layer, False)
            root = QgsProject.instance().layerTreeRoot()
            root.insertLayer(2, buffer_layer)  # Yerleşim noktalarının altına ekle
        
        # Render ayarlarını optimize et
        self.settlement_layer.renderer().setForceRasterRender(False)
        
        # Katmanı yenile
        self.settlement_layer.triggerRepaint()
        
        # Canvas'ı zorla yenile
        if self.iface and self.iface.mapCanvas():
            self.iface.mapCanvas().refreshAllLayers()
            QtCore.QTimer.singleShot(100, lambda: self.iface.mapCanvas().refresh())

    def on_settlement_distance_changed(self, value):
        """Yerleşim noktası mesafesi değiştiğinde çağrılır"""
        # Önce yerleşim noktalarını güncelle (bu buffer'ları da güncelleyecek)
        self.update_settlement_filter()
        
        # Sonra deprem verilerini filtrele
        if self.earthquake_data is not None:
            self.apply_earthquake_filter()

    def update_settlement_distance_spinbox(self):
        """Yerleşim noktası mesafesi spinbox'ının durumunu güncelle"""
        # Hem deprem hem de yerleşim noktaları verileri yüklüyse aktif et
        should_enable = (self.earthquake_data is not None and 
                        self.settlement_layer is not None and 
                        self.settlement_layer.isValid())
        
        self.settlementDistanceSpinBox.setEnabled(should_enable)
        if not should_enable:
            self.settlementDistanceSpinBox.setValue(0)