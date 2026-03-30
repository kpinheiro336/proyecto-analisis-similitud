"""
Análisis de similitud entre productos Xiaomi en Amazon España.

Este script hace web scraping de Amazon, extrae los productos de una búsqueda
y luego compara sus títulos usando el algoritmo de Ratcliff/Obershelp
(implementado en difflib.SequenceMatcher) para encontrar productos similares.

La similitud se muestra en porcentaje y se presenta en una tabla formateada.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from datetime import datetime
import csv
import time
import os

# ──────────────────────────────────────────────
# Configuración general del script
# ──────────────────────────────────────────────
BUSQUEDA = "xiaomi"
URL = f"https://www.amazon.es/s?k={BUSQUEDA}"
UMBRAL_SIMILITUD = 0.75  # 75 % de similitud mínima para mostrar un par


def extraer_precio(producto):
    """Intenta sacar el precio de un producto de Amazon.

    Primero busca el precio en el elemento oculto (a-offscreen), que suele ser
    el más fiable. Si no lo encuentra, arma el precio juntando la parte entera
    y la parte decimal desde los spans separados.

    Devuelve un float con el precio, o None si no pudo extraerlo.
    """
    # Primer intento: el precio suele estar escondido en un span para lectores de pantalla
    offscreen = producto.select_one("span.a-price span.a-offscreen")
    if offscreen:
        texto = offscreen.get_text(strip=True)
        # Limpiamos el texto: quitamos el símbolo €, espacios raros, puntos de miles
        limpio = texto.replace("€", "").replace("\xa0", "").strip()
        limpio = limpio.replace(".", "").replace(",", ".")
        try:
            return float(limpio)
        except ValueError:
            pass

    # Segundo intento: armamos el precio con la parte entera y decimal por separado
    entero_tag = producto.select_one("span.a-price-whole")
    decimal_tag = producto.select_one("span.a-price-fraction")
    if entero_tag:
        entero = entero_tag.get_text(strip=True).replace(".", "").replace(",", "")
        decimal = decimal_tag.get_text(strip=True) if decimal_tag else "00"
        try:
            return float(f"{entero}.{decimal}")
        except ValueError:
            pass

    return None


def es_producto_real(producto):
    """Filtra los bloques que no son productos reales (publicidad, banners, etc.)."""
    # Si no tiene un ASIN (identificador de Amazon), no es un producto de verdad
    asin = producto.get("data-asin", "").strip()
    if not asin:
        return False
    # Si no tiene título, tampoco nos sirve
    if not producto.select_one("h2 span"):
        return False
    return True


def scrape_amazon(url):
    """Abre Safari, hace la búsqueda en Amazon y devuelve los productos encontrados."""
    driver = webdriver.Safari()
    try:
        driver.get(url)

        # Esperamos a que aparezcan los resultados de búsqueda en la página
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[data-component-type="s-search-result"]')
            )
        )
        # Pequeña pausa extra por si hay contenido que carga dinámicamente
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "lxml")
    finally:
        # Cerramos Safari pase lo que pase
        driver.quit()

    productos = soup.select('div[data-component-type="s-search-result"]')
    lista_productos = []

    for producto in productos:
        if not es_producto_real(producto):
            continue

        titulo_tag = producto.select_one("h2 span")
        titulo_texto = titulo_tag.get_text(strip=True)

        precio_float = extraer_precio(producto)
        if precio_float is None:
            continue

        lista_productos.append({
            "titulo": titulo_texto,
            "precio": precio_float,
        })

    return lista_productos


def mostrar_productos(lista):
    """Muestra una tabla con todos los productos encontrados, su precio y un índice.

    Devuelve el texto formateado de la tabla para poder guardarlo después.
    """
    if not lista:
        msg = "\n  No se encontraron productos.\n"
        print(msg)
        return msg

    lineas = []

    # Calculamos el ancho máximo del título para que la tabla quede alineada
    ancho_titulo = max(len(p["titulo"][:80]) for p in lista)
    ancho_titulo = max(ancho_titulo, len("Producto"))

    separador = f"  +{'─' * 5}+{'─' * (ancho_titulo + 2)}+{'─' * 12}+"

    lineas.append(f"\n{'=' * 60}")
    lineas.append(f"  RESULTADOS: {len(lista)} productos encontrados")
    lineas.append(f"{'=' * 60}\n")
    lineas.append(separador)
    lineas.append(f"  | {'#':>3} | {'Producto':<{ancho_titulo}} | {'Precio':>10} |")
    lineas.append(separador)

    for i, p in enumerate(lista, 1):
        titulo_corto = p["titulo"][:80]
        lineas.append(f"  | {i:>3} | {titulo_corto:<{ancho_titulo}} | {p['precio']:>8.2f} € |")

    lineas.append(separador)

    texto = "\n".join(lineas)
    print(texto)
    return texto


def comparar_similitud(lista, umbral=UMBRAL_SIMILITUD):
    """Compara todos los títulos entre sí y muestra una tabla con los pares similares.

    Usa el algoritmo de Ratcliff/Obershelp (SequenceMatcher) para calcular
    la similitud entre cada par de títulos. Solo muestra los que superan el umbral.
    La similitud se expresa en porcentaje (0 % - 100 %).

    Devuelve el texto formateado de la tabla para poder guardarlo después.
    """
    if len(lista) < 2:
        msg = "\n  Se necesitan al menos 2 productos para comparar similitud.\n"
        print(msg)
        return msg

    lineas = []

    # Primero recopilamos todos los pares que superan el umbral
    pares_similares = []
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            t1 = lista[i]["titulo"]
            t2 = lista[j]["titulo"]
            ratio = SequenceMatcher(None, t1.lower(), t2.lower()).ratio()
            if ratio >= umbral:
                pares_similares.append({
                    "producto_1": t1[:60],
                    "producto_2": t2[:60],
                    "precio_1": lista[i]["precio"],
                    "precio_2": lista[j]["precio"],
                    "similitud": ratio * 100,  # Convertimos a porcentaje
                })

    lineas.append(f"\n{'=' * 60}")
    lineas.append("  ANÁLISIS DE SIMILITUD (Ratcliff/Obershelp)")
    lineas.append(f"  Umbral mínimo: {umbral * 100:.0f} %")
    lineas.append(f"{'=' * 60}\n")

    if not pares_similares:
        lineas.append(f"  No se encontraron pares con similitud ≥ {umbral * 100:.0f} %.\n")
        texto = "\n".join(lineas)
        print(texto)
        return texto

    # Armamos la tabla de resultados
    ancho_prod = 60
    separador = f"  +{'─' * (ancho_prod + 2)}+{'─' * (ancho_prod + 2)}+{'─' * 10}+{'─' * 12}+{'─' * 12}+"

    lineas.append(separador)
    lineas.append(
        f"  | {'Producto 1':<{ancho_prod}} "
        f"| {'Producto 2':<{ancho_prod}} "
        f"| {'Similitud':>8} "
        f"| {'Precio 1':>10} "
        f"| {'Precio 2':>10} |"
    )
    lineas.append(separador)

    for par in sorted(pares_similares, key=lambda x: x["similitud"], reverse=True):
        lineas.append(
            f"  | {par['producto_1']:<{ancho_prod}} "
            f"| {par['producto_2']:<{ancho_prod}} "
            f"| {par['similitud']:>7.1f} % "
            f"| {par['precio_1']:>8.2f} € "
            f"| {par['precio_2']:>8.2f} € |"
        )

    lineas.append(separador)
    lineas.append(f"\n  Total de pares similares encontrados: {len(pares_similares)}\n")

    texto = "\n".join(lineas)
    print(texto)
    return texto


def guardar_productos_csv(lista, nombre_archivo):
    """Guarda la lista de productos en un CSV que se abre bien en Excel y Numbers.

    Usa punto y coma como separador para que Excel en español lo interprete
    correctamente sin necesidad de importar manualmente.
    """
    escritorio = os.path.join(os.path.expanduser("~"), "Desktop")
    ruta = os.path.join(escritorio, nombre_archivo)

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["#", "Producto", "Precio (€)"])
        for i, p in enumerate(lista, 1):
            writer.writerow([i, p["titulo"], f"{p['precio']:.2f}"])

    return ruta


def guardar_similitud_csv(lista, nombre_archivo, umbral=UMBRAL_SIMILITUD):
    """Guarda los pares similares en un CSV compatible con Excel y Numbers.

    Recalcula los pares a partir de la lista original para tener los datos
    completos (no truncados) en la hoja de cálculo.
    """
    escritorio = os.path.join(os.path.expanduser("~"), "Desktop")
    ruta = os.path.join(escritorio, nombre_archivo)

    # Recopilamos los pares que superan el umbral
    pares = []
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            t1 = lista[i]["titulo"]
            t2 = lista[j]["titulo"]
            ratio = SequenceMatcher(None, t1.lower(), t2.lower()).ratio()
            if ratio >= umbral:
                pares.append((t1, t2, ratio * 100, lista[i]["precio"], lista[j]["precio"]))

    # Ordenamos de mayor a menor similitud
    pares.sort(key=lambda x: x[2], reverse=True)

    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Producto 1", "Producto 2", "Similitud (%)", "Precio 1 (€)", "Precio 2 (€)"])
        for t1, t2, sim, p1, p2 in pares:
            writer.writerow([t1, t2, f"{sim:.1f}", f"{p1:.2f}", f"{p2:.2f}"])

    return ruta


def preguntar_guardar(lista_productos):
    """Pregunta al usuario si quiere guardar los resultados como CSV para Excel/Numbers."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'=' * 60}")
    print("  ¿Quieres guardar los resultados en tu ordenador?")
    print("  (Se guardarán como CSV, compatible con Excel y Numbers)")
    print(f"{'=' * 60}\n")

    # Preguntar por la tabla de productos
    respuesta = input("  ¿Guardar la tabla de productos? (s/n): ").strip().lower()
    if respuesta in ("s", "si", "sí", "y", "yes"):
        nombre = f"productos_xiaomi_{timestamp}.csv"
        ruta = guardar_productos_csv(lista_productos, nombre)
        print(f"  ✅ Tabla de productos guardada en: {ruta}")
    else:
        print("  ⏭️  No se guardó la tabla de productos.")

    # Preguntar por la tabla de similitud
    if len(lista_productos) >= 2:
        respuesta = input("  ¿Guardar la tabla de similitud? (s/n): ").strip().lower()
        if respuesta in ("s", "si", "sí", "y", "yes"):
            nombre = f"similitud_xiaomi_{timestamp}.csv"
            ruta = guardar_similitud_csv(lista_productos, nombre)
            print(f"  ✅ Tabla de similitud guardada en: {ruta}")
        else:
            print("  ⏭️  No se guardó la tabla de similitud.")

    print("\n  ¡Listo! Hasta la próxima. 👋\n")


# ──────────────────────────────────────────────
# Punto de entrada del script
# ──────────────────────────────────────────────
if __name__ == "__main__":
    productos = scrape_amazon(URL)
    mostrar_productos(productos)
    comparar_similitud(productos)
    preguntar_guardar(productos)


