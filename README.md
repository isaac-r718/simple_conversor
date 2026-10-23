*Creado con apoyo de inteligencia artificial.*

# simple_conversor

Aplicación de escritorio para extraer el texto de documentos y guardarlo en
Markdown, un formato legible y sencillo de procesar para herramientas de IA.
La conversión se realiza localmente; los documentos no se envían a servicios
externos.

## Requisitos

- Python 3.10 o superior.
- Tkinter, incluido normalmente con Python para Windows.

## Instalación

```bash
python -m venv .venv
```

Activa el entorno virtual y luego instala las dependencias:

```bash
python -m pip install -r requirements.txt
```

En Windows PowerShell, activa el entorno con:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Interfaz gráfica

```bash
python simple_conversor_gui.py
```

Selecciona la carpeta de origen y la carpeta de destino con los botones
**Cambiar...** y pulsa **Convertir**. Por defecto se proponen las carpetas
`not_md` y `md` del proyecto. Los archivos Markdown existentes se omiten salvo
que marques la opción para reemplazarlos.

## Línea de comandos

Sin argumentos, convierte los archivos compatibles de `not_md` a `md`:

```bash
python simple_conversor.py
```

También puedes indicar las carpetas y permitir que se reemplacen los
resultados existentes:

```bash
python simple_conversor.py ruta/a/documentos --output ruta/a/markdown
python simple_conversor.py ruta/a/documentos --output ruta/a/markdown --overwrite
```

Para convertir un único archivo, indica como destino un archivo `.md`:

```bash
python simple_conversor.py documento.pdf --output documento.md
```

## Formatos compatibles

PDF, DOCX, ODT, RTF, HTML, TXT y Markdown. Se conservan títulos, listas y
tablas cuando es posible. Los PDF deben contener texto seleccionable; los
escaneos requieren OCR, que no está incluido.

## Datos y privacidad

El programa no sube documentos ni los comparte. Los archivos de origen, los
Markdown generados y los entornos locales están excluidos de Git mediante
`.gitignore`. Revisa los archivos antes de compartir el proyecto y evita
incluir documentos privados en un repositorio público.

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Consulta [LICENSE](LICENSE).
