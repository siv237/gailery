# FLIR Thermal Image Conversion (BV6600Pro)

## Извлечение и преобразование RawThermalImage в тепловую карту

### Формат данных
- RawThermalImage — PNG mode "I" (32-bit int), реально 16-bit данные
- Пиксели хранятся как uint16 в big-endian (network byte order)
- PIL на x86 (little-endian) читает байты перевёрнутыми → **нужен byte swap**

### Byte swap
```python
arr = np.array(pil_img, dtype=np.uint16)
# Меняем байты местами: (high_byte, low_byte) → (low_byte, high_byte)
fixed = ((arr & 0xff) << 8) | (arr >> 8)
```

**Детекция:** после свапа значения упаковываются в компактный диапазон (upper byte range << lower byte range). Без свапа upper byte = 0-255, lower byte = 2-15 значений (шум).

### Параметры из EXIF
Извлекаются через exiftool:
| Тег | Переменная | Пример (вода) |
|-----|------------|---------------|
| Emissivity | E | 0.90 |
| SubjectDistance | OD | 0.44 m |
| AtmosphericTemperature | ATemp | 20.0°C |
| ReflectedApparentTemperature | RTemp | 25.0°C |
| IRWindowTemperature | IRWTemp | 34.3°C |
| IRWindowTransmission | IRT | 0.82 |
| RelativeHumidity | RH | 50.0% |
| PlanckR1 | PR1 | 17938.449 / 5201.75 |
| PlanckB | PB | 1435 / 1470 |
| PlanckF | PF | 1 |
| PlanckO | PO | -1830 / -1565 |
| PlanckR2 | PR2 | 0.0125 |

Два набора Planck-параметров (высокотемпературный/низкотемпературный) — камера выбирает автоматически. EXIF-теги каждого файла содержат активный набор.

### Преобразование raw → °C (raw2temp)
Полная формула из Thermimage R package (Minkina & Dudzik):

1. **Водяной пар в воздухе** (h₂o):
   ```
   h2o = (RH/100) * exp(1.5587 + 0.06939*ATemp - 0.00027816*ATemp² + 0.00000068455*ATemp³)
   ```

2. **Атмосферная пропускная способность** (tau₁, tau₂):
   ```
   sd2 = sqrt(OD/2)
   tau = ATX*exp(-sd2*(ATA1+ATB1*sqrt(h2o))) + (1-ATX)*exp(-sd2*(ATA2+ATB2*sqrt(h2o)))
   ```
   Константы: ATA1=0.006569, ATA2=0.01262, ATB1=-0.002276, ATB2=-0.00667, ATX=1.9

3. **Излучение среды** в raw-единицах:
   ```
   raw_refl = PR1/(PR2*(exp(PB/(RTemp+273.15))-PF)) - PO       # отражённое от объекта
   raw_atm  = PR1/(PR2*(exp(PB/(ATemp+273.15))-PF)) - PO       # атмосферное
   raw_wind = PR1/(PR2*(exp(PB/(IRWTemp+273.15))-PF)) - PO     # окно
   ```

4. **Ослабленное излучение** с коэффициентами E, tau, IRT:
   ```
   raw_obj = raw / (E * tau1 * IRT * tau2)
           - (1-E)/E * raw_refl
           - (1-tau1)/E/tau1 * raw_atm
           - emiss_wind/E/tau1/IRT * raw_wind
           - (1-tau2)/E/tau1/IRT/tau2 * raw_atm
   ```

5. **Температура по Planck**:
   ```
   temp_C = PB / log(PR1 / (PR2 * (raw_obj + PO)) + PF) - 273.15
   ```

### Палитра (224 цвета, iron)
Извлекается из EXIF через `-Palette` (672 bytes = 224×3).
Хранится в YCbCr (BT.601), конвертируется в RGB:
```python
r = y + 1.402*cr
g = y - 0.344136*cb - 0.714136*cr
b = y + 1.772*cb
```
Где y = Y/255, cb = (Cb-128)/255, cr = (Cr-128)/255.

Применяется к температуре с билинейной интерполяцией между соседними цветами палитры.

### Fallback
Если Planck даёт среднюю температуру вне диапазона [-50, 150]°C — используется raw/1000 с клиппингом 1-99 перцентилей.

### Ключевые файлы
- `src/api/photos.py` — эндпоинт `/flir_raw_palette` (GET)
- `src/frontend/flir_test/align_fixed.html` — инструмент отладки совмещения
- `src/flir_parser.py` — парсер FLIR-метаданных

### Ссылки
- [Thermimage R package](https://github.com/gtatters/Thermimage)
- [flir_image_extractor.py](https://github.com/ManishSahu53/read_thermal_temperature/blob/master/flir_image_extractor.py)
- [ExifTool FLIR Tags](https://www.exiftool.org/TagNames/FLIR.html)
