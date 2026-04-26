import osmnx as ox
import networkx as nx
import pandas as pd
import matplotlib.pyplot as plt
import os


def calcular_pesos(fila):
    """
    Calcula dos escenarios de tiempo para cada calle:
    Uno para tráfico normal y otro para hora pico para las calles y los tiempos de respuesta.
    """
    tipo_calle = fila['highway']
    tiempo_base = fila['travel_time']
    vias_principales = ['motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link']

    if isinstance(tipo_calle, list):
        es_principal = any(v in vias_principales for v in tipo_calle)
    else:
        es_principal = tipo_calle in vias_principales

    # ESCENARIO 1: Tráfico Normal (La ambulancia va a buena velocidad, asumimos tráfico normal)
    tiempo_normal = tiempo_base * 2

    # ESCENARIO 2: Hora Pico
    if es_principal:
        tiempo_pico = tiempo_base * 4.5  # Vías principales colapsadas
    else:
        tiempo_pico = tiempo_base * 2.7  # Vías secundarias con tráfico moderado

    # Devolvemos ambos valores para crear dos columnas en Pandas
    return pd.Series([tiempo_normal, tiempo_pico])


def extraer_calles_de_ruta(G, ruta):
    """
    Recorre los nodos de la ruta ganadora y extrae los nombres de las calles,
    evitando imprimir la misma calle repetida varias veces.
    """
    nombres_calles = []

    for i in range(len(ruta) - 1):
        u = ruta[i]
        v = ruta[i + 1]

        # Obtenemos los datos de la calle que conecta el nodo u con el v
        datos_calle = G.get_edge_data(u, v)
        if datos_calle:
            # osmnx usa MultiDiGraphs, tomamos la primera arista disponible [0]
            data = datos_calle[0]
            nombre = data.get('name', 'Calle sin nombre')

            # A veces osmnx devuelve una lista si dos calles se fusionan
            if isinstance(nombre, list):
                nombre = nombre[0]

            # Solo agregamos la calle si es diferente a la última que guardamos
            if not nombres_calles or nombres_calles[-1] != nombre:
                nombres_calles.append(str(nombre))

    return nombres_calles

def simular_despacho(G, hospitales_nodos, lat_acc, lng_acc, hora, dia, nombre_prueba):
    """
    Simula el despacho evaluando el día de la semana y la hora para aplicar el escenario de tráfico correcto.
    """
    print(f"\n============================================================")
    print(f"PRUEBA: {nombre_prueba}")

    dia_limpio = dia.strip().lower()

    # Lógica de decisión de tráfico basada en el DÍA y la HORA
    if dia_limpio == 'domingo':
        es_hora_pico = False
        estado_trafico = "FLUIDO (Domingo)"
    elif dia_limpio in ['sábado', 'sabado']:
        # Pico comercial en sábado: 12 PM a 8 PM
        es_hora_pico = (12 <= hora < 20)
        estado_trafico = "ALTO" if es_hora_pico else "REGULAR (Fluido)"
    else:
        # Lunes a Viernes: Pico laboral de 6-9 AM y 5-9 PM (17 a 21 hrs)
        es_hora_pico = (6 <= hora < 9) or (17 <= hora < 21)
        estado_trafico = "CRÍTICO (Hora Pico Laboral)" if es_hora_pico else "REGULAR (Fluido)"

    peso_usar = 'tiempo_hora_pico' if es_hora_pico else 'tiempo_normal'

    print(f"Momento del reporte: {dia.capitalize()}, {hora:02d}:00 hrs")
    print(f"Tráfico:{estado_trafico}")
    print(f"============================================================")

    nodo_accidente = ox.distance.nearest_nodes(G, X=lng_acc, Y=lat_acc)
    tiempos_respuesta = {}
    rutas = {}

    for nombre_hospital, nodo_origen in hospitales_nodos.items():
        try:
            tiempo_seg = nx.shortest_path_length(G, source=nodo_origen, target=nodo_accidente, weight=peso_usar)
            ruta = nx.shortest_path(G, source=nodo_origen, target=nodo_accidente, weight=peso_usar)
            tiempos_respuesta[nombre_hospital] = tiempo_seg / 60
            rutas[nombre_hospital] = ruta
        except nx.NetworkXNoPath:
            pass  # Ignoramos en silencio si un hospital no tiene ruta

    mejor_hospital = min(tiempos_respuesta, key=tiempos_respuesta.get)
    mejor_tiempo = tiempos_respuesta[mejor_hospital]

    print("\n--- TIEMPOS DE RESPUESTA EVALUADOS (ORDENADOS) ---")
    hospitales_ordenados = sorted(tiempos_respuesta.items(), key=lambda item: item[1])

    for nombre, tiempo in hospitales_ordenados:
        indicador = "(ÓPTIMO)" if nombre == mejor_hospital else ""
        print(f" - {nombre}: {tiempo:.2f} min {indicador}")

    print(f"============================================================")
    print("\nDECISIÓN OPERATIVA")
    print(f" > Despachar unidad desde: {mejor_hospital}")
    print(f" > Tiempo estimado: {mejor_tiempo:.2f} minutos\n")

    # INDICACIONES VIALES (Las 3 Mejores)
    print("INDICACIONES DE NAVEGACIÓN:")
    # Tomamos solo los 3 primeros de la lista ordenada
    for nombre, tiempo in hospitales_ordenados[:3]:
        ruta_hospital = rutas[nombre]
        calles = extraer_calles_de_ruta(G, ruta_hospital)
         # Filtramos las "Calles sin nombre" para que se vea más limpio
        calles_limpias = [c for c in calles if c != 'Calle sin nombre']
        camino_texto = " -> ".join(calles_limpias)
        print(f"\n{nombre} ({tiempo:.2f} min):")
        print(f"Ruta: {camino_texto}")

    print(f"============================================================")

    # VISUALIZACIÓN DE RED CON JERARQUÍA VISUAL
    rutas_a_graficar = []
    colores_rutas = []
    anchos_rutas = []

    color_cian_transparente = '#00FFFF4D'
    color_rojo_solido = '#FF0000FF'

    for nombre, ruta in rutas.items():
        if nombre != mejor_hospital:
            rutas_a_graficar.append(ruta)
            colores_rutas.append(color_cian_transparente)
            anchos_rutas.append(1.5)

    rutas_a_graficar.append(rutas[mejor_hospital])
    colores_rutas.append(color_rojo_solido)
    anchos_rutas.append(4)

    fig, ax = ox.plot_graph_routes(
        G, rutas_a_graficar,
        route_colors=colores_rutas,
        route_linewidths=anchos_rutas,
        node_size=0, bgcolor='#111111', show=False, close=False
    )

    ax.scatter(lng_acc, lat_acc, c='yellow', s=120, zorder=5, marker='X')

    for nombre, nodo_hosp in hospitales_nodos.items():
        x_hosp = G.nodes[nodo_hosp]['x']
        y_hosp = G.nodes[nodo_hosp]['y']

        if nombre == mejor_hospital:
            ax.scatter(x_hosp, y_hosp, c='lime', s=100, zorder=5, marker='o')
        else:
            ax.scatter(x_hosp, y_hosp, c='white', s=50, alpha=0.6, zorder=5, marker='o')

    plt.title(f"{nombre_prueba} ({dia.capitalize()} {hora:02d}:00 hrs) - {estado_trafico}", color='white', fontsize=11)

    #Guardar las imágenes de las rutas
    carpeta = "reportes_viales"
    if not os.path.exists(carpeta):
        os.makedirs(carpeta)

    # Limpiamos el nombre: quitamos espacios, dos puntos y comas
    nombre_limpio = nombre_prueba.replace(' ', '_').replace(':', '').replace(',', '')
    nombre_archivo = f"{nombre_limpio}_{dia}_{hora}hrs.png"
    ruta_guardado = os.path.join(carpeta, nombre_archivo)

    # Guardamos la figura antes de mostrarla
    fig.savefig(ruta_guardado, dpi=300, bbox_inches='tight', facecolor='#111111')
    plt.show()


def main():
    archivo_grafo = "monterrey_red_ambulancias.graphml"

    if os.path.exists(archivo_grafo):
        print("Cargando el mapa desde el archivo local...")
        G = ox.load_graphml(archivo_grafo)
        for u, v, key, data in G.edges(keys=True, data=True):
            if 'tiempo_normal' in data:
                data['tiempo_normal'] = float(data['tiempo_normal'])
            if 'tiempo_hora_pico' in data:
                data['tiempo_hora_pico'] = float(data['tiempo_hora_pico'])
    else:
        print("Descargando el mapa...")
        punto_central = (25.6750, -100.3200)
        G = ox.graph_from_point(punto_central, dist=8000, network_type='drive')
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)

        calles_df = ox.graph_to_gdfs(G, nodes=False)
        calles_df[['tiempo_normal', 'tiempo_hora_pico']] = calles_df.apply(calcular_pesos, axis=1)

        nx.set_edge_attributes(G, values=calles_df['tiempo_normal'].to_dict(), name='tiempo_normal')
        nx.set_edge_attributes(G, values=calles_df['tiempo_hora_pico'].to_dict(), name='tiempo_hora_pico')

        print("Guardando grafo...")
        ox.save_graphml(G, filepath=archivo_grafo)
        print("¡Grafo guardado exitosamente!")

    print("Configurando las Bases (Hospitales)...")
    coordenadas_bases = {
        "Cruz Roja (Centro)": (25.6946, -100.3168),
        "Hospital Universitario": (25.6885, -100.3490),
        "Hospital San José": (25.6668, -100.3487),
        "ISSSTE Hospital Regional Monterrey": (25.708726, -100.359498),
        "Hospital Del Maestro": (25.709673, -100.347504),
        "Hospital Christus Muguerza": (25.686964, -100.308308),
        "PRONAMED Salud Integral": (25.718261, -100.339537),
        "CRUM NL Centro Regulador de Urgencias Médicas": (25.663481, -100.287160),
        "Kipcalm Emergencias": (25.666187, -100.336744),
        "Ambulancias MED-CARE": (25.704095, -100.343308),
        "Hospital Monterrey": (25.689203, -100.287428),
        "Hospital Zambrano Hellion TecSalud": (25.647517, -100.333603),
        "OCA Hospital Auna": (25.681540, -100.318406),
        "Protección Civil": (25.672016, -100.282699),
        "Protección Civil del Estado": (25.659964, -100.333114),
        "Hospital General de Zona con Medicina Familiar": (25.670058, -100.295699)
    }

    hospitales_nodos = {}
    for nombre, (lat, lng) in coordenadas_bases.items():
        hospitales_nodos[nombre] = ox.distance.nearest_nodes(G, X=lng, Y=lat)

    pruebas = [
        {"nombre": "Choque en Constitución", "lat": 25.6695, "lng": -100.3415, "hora": 18, "dia": "Lunes"},
        {"nombre": "Choque en Constitución", "lat": 25.6695, "lng": -100.3415, "hora": 18, "dia": "Domingo"},
        {"nombre": "Incidente en Fundidora", "lat": 25.6800, "lng": -100.2860, "hora": 13, "dia": "Miercoles"},
        {"nombre": "Emergencia en Tec de Monterrey", "lat": 25.6515, "lng": -100.2900, "hora": 18, "dia": "Jueves"},
        {"nombre": "Volcadura en Galerías Monterrey", "lat": 25.6805, "lng": -100.3450, "hora": 0, "dia": "Sabado"},
        {"nombre": "Altercado automovilístico en Leones", "lat": 25.695759, "lng": -100.343029, "hora": 18, "dia": "Martes"},
        {"nombre": "Altercado automovilístico en Leones", "lat": 25.695759, "lng": -100.343029, "hora": 12, "dia": "Domingo"}
    ]

    for prueba in pruebas:
        simular_despacho(G, hospitales_nodos, prueba["lat"], prueba["lng"], prueba["hora"], prueba["dia"],prueba["nombre"])


    # MODO INTERACTIVO (DESPACHO EN TIEMPO REAL)
    print("\n============================================================")
    print(" SISTEMA DE DESPACHO INTERACTIVO INICIADO")
    print("============================================================")

    dias_validos = ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo']
    try:
        while True:
            print("\nIngresa la dirección del accidente, o las coordenadas (Ej. 25.669, -100.341)")
            entrada_usuario = input("   (Escribe 'salir' para terminar):\n> ").strip()

            if entrada_usuario.lower() in ['salir', 'exit', 'parar', 'terminar', 'cerrar']:
                print("\nApagando el Sistema de Despacho EMMI.")
                break

            es_coordenada = False
            partes = entrada_usuario.split(',')

            if len(partes) == 2:
                try:
                    # Intentamos convertir las dos partes a números decimales
                    lat_usuario = float(partes[0].strip())
                    lng_usuario = float(partes[1].strip())
                    es_coordenada = True
                    nombre_emergencia = f"Coords_{lat_usuario}_{lng_usuario}"
                except ValueError:
                    # Si falla, significa que era texto con una coma
                    es_coordenada = False

            try:
                # Si NO son coordenadas, usamos el satélite para traducir el texto
                if not es_coordenada:
                    query_busqueda = f"{entrada_usuario}, Monterrey, Nuevo Leon, Mexico"
                    lat_usuario, lng_usuario = ox.geocode(query_busqueda)
                    nombre_emergencia = entrada_usuario
                else:
                    print("\nCoordenadas detectadas directamente. Omitiendo satélite...")
                    print(f"¡Ubicación fijada! -> Lat: {lat_usuario:.6f}, Lng: {lng_usuario:.6f}")
                    # --- VALIDACIÓN DEL DÍA ---
                while True:
                    dia_str = input(
                        "\nIngresa el día de la semana (Ej. 'Lunes', 'Sabado', 'Domingo'):\n> ").strip().lower()
                    if dia_str in dias_validos:
                        dia_usuario = dia_str.capitalize()
                        break
                    else:
                        print(" Día no reconocido. Por favor, escribe un día válido.")

                # --- VALIDACIÓN DE LA HORA ---
                while True:
                    hora_str = input("Ingresa la hora del reporte (Formato 24h, 0 al 23):\n> ").strip()
                    if hora_str.isdigit() and 0 <= int(hora_str) <= 23:
                        hora_usuario = int(hora_str)
                        break
                    else:
                        print(" Hora inválida. Ingresa un número entre 0 y 23.")

                print("\nCalculando matriz de rutas...")
                simular_despacho(G, hospitales_nodos, lat_usuario, lng_usuario, hora_usuario, dia_usuario,f"Emergencia en {nombre_emergencia}")

            except Exception as e:
                print(f"\nError: No pudimos localizar '{entrada_usuario}' en el mapa.")
                print("Pruebe con una ubicación válida o con coordenadas de Longitud y latitud")
    except KeyboardInterrupt:
        print("\nApagando el Sistema de Despacho EMMI.")

if __name__ == "__main__":
    main()