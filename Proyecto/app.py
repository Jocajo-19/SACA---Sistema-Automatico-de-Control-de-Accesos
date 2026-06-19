from flask import Flask, request, jsonify, render_template_string, redirect, url_for
import MySQLdb
import qrcode
import io
import base64

app = Flask(__name__)
app.json.ensure_ascii = False

DB_CONFIG = {
    "host": "db",
    "user": "admin_torno",
    "passwd": "torno_futbol_pass",
    "db": "control_accesos",
    "port": 3306
}

AFORO_MAXIMO = 5  # Límite de personas permitidas para la simulación

@app.route("/validar", methods=["POST"])
def validar_acceso():
    data = request.get_json()
    if not data or "codigo_qr" not in data or "puerta" not in data:
        return jsonify({"error": "Datos incompletos"}), 400
        
    codigo = data["codigo_qr"]
    puerta_torno = data["puerta"]
    db, cursor = None, None
    
    try:
        db = MySQLdb.connect(**DB_CONFIG)
        cursor = db.cursor(MySQLdb.cursors.DictCursor)
        
        # Consultamos el socio y su ubicación/puerta asignada (guardada en el campo 'estado')
        # Usamos un truco en la base de datos: guardamos la puerta y si está 'DENTRO' o 'FUERA'
        cursor.execute("SELECT id_socio, nombre, estado FROM socios WHERE codigo_qr = %s", (codigo,))
        socio = cursor.fetchone()
        
        id_socio = None
        resultado = "denegado"
        motivo = ""
        
        if socio:
            id_socio = socio["id_socio"]
            datos_estado = socio["estado"].split("|")
            puerta_asignada = datos_estado[0]
            
            # Comprobamos si el usuario ya está dentro (Lógica Anti-Passback)
            situacion_actual = datos_estado[1] if len(datos_estado) > 1 else "FUERA"
            
            # Determinar si el torno actual es de ENTRADA o SALIDA basándonos en la petición
            es_salida = "salida" in puerta_torno.lower()
            
            if es_salida:
                if situacion_actual == "FUERA":
                    resultado = "denegado"
                    motivo = f"Error Anti-Passback: {socio['nombre']} intenta SALIR pero el sistema consta que ya está FUERA."
                else:
                    resultado = "concedido"
                    motivo = f"Salida autorizada para {socio['nombre']} por {puerta_torno}."
                    # Actualizamos su estado a FUERA
                    cursor.execute("UPDATE socios SET estado = %s WHERE id_socio = %s", (f"{puerta_asignada}|FUERA", id_socio))
            else:
                # Es un intento de ENTRADA
                if situacion_actual == "DENTRO":
                    resultado = "denegado"
                    motivo = f"Error Anti-Passback: {socio['nombre']} intenta ENTRAR pero su QR ya está DENTRO."
                elif puerta_torno.lower() != puerta_asignada.lower():
                    resultado = "denegado"
                    motivo = f"Puerta Incorrecta. Intenta entrar por {puerta_torno} pero su pase es de {puerta_asignada}."
                else:
                    resultado = "concedido"
                    motivo = f"Acceso OK para {socio['nombre']} en {puerta_torno}."
                    # Actualizamos su estado a DENTRO
                    cursor.execute("UPDATE socios SET estado = %s WHERE id_socio = %s", (f"{puerta_asignada}|DENTRO", id_socio))
        else:
            motivo = "Codigo QR no registrado o invalido"
            
        cursor.execute("INSERT INTO registro_accesos (id_socio, codigo_escaneado, puerta, resultado, motivo) VALUES (%s, %s, %s, %s, %s)", (id_socio, codigo, puerta_torno, resultado, motivo))
        db.commit()
        return jsonify({"status": resultado, "abrir_torno": True if resultado == "concedido" else False, "mensaje": motivo}), 200
    except Exception as e:
        return jsonify({"status": "error", "mensaje": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if db: db.close()

@app.route("/registro", methods=["GET", "POST"])
def registro_usuario():
    db, cursor = None, None
    try:
        db = MySQLdb.connect(**DB_CONFIG)
        cursor = db.cursor(MySQLdb.cursors.DictCursor)
        
        # CONTROL DE AFORO: Contamos cuántos QR totales se han emitido
        cursor.execute("SELECT COUNT(*) as total FROM socios")
        total_registrados = cursor.fetchone()["total"]
        
        if request.method == "POST":
            if total_registrados >= AFORO_MAXIMO:
                return f"""
                <div style="font-family:sans-serif; text-align:center; margin-top:50px; color:#7f8c8d; background:#eaeded; padding:30px; border-radius:8px; max-width:500px; margin-left:auto; margin-right:auto; box-shadow:0 4px 10px rgba(0,0,0,0.05);">
                    <h2>🏟️ Aforo Completo</h2>
                    <p style="font-size:16px;">Lo sentimos, se ha alcanzado el límite de pases disponibles ({AFORO_MAXIMO}/{AFORO_MAXIMO}) para este evento.</p>
                    <a href="/dashboard" style="display:inline-block; margin-top:15px; background:#34495e; color:white; padding:10px 20px; text-decoration:none; border-radius:4px; font-weight:bold;">Ver Monitor General</a>
                </div>
                """, 403
                
            nombre = request.form.get("nombre")
            identificador = request.form.get("identificador").strip()
            puerta_seleccionada = request.form.get("puerta")
            
            codigo_qr_generado = f"QR_ESTADIO_{identificador.upper()}"
            
            cursor.execute("SELECT nombre FROM socios WHERE codigo_qr = %s", (codigo_qr_generado,))
            ocupado = cursor.fetchone()
            
            if ocupado:
                return f"""
                <div style="font-family:sans-serif; text-align:center; margin-top:50px; color:#c0392b; background:#fdf2f2; padding:30px; border-radius:8px; max-width:500px; margin-left:auto; margin-right:auto; box-shadow:0 4px 10px rgba(0,0,0,0.05);">
                    <h2>❌ Registro Invalidado</h2>
                    <p style="font-size:16px;">El identificador <strong>{identificador}</strong> ya está registrado.</p>
                    <a href="/registro" style="display:inline-block; margin-top:15px; background:#c0392b; color:white; padding:10px 20px; text-decoration:none; border-radius:4px; font-weight:bold;">Volver</a>
                </div>
                """, 400
            
            # Guardamos la puerta y el estado inicial 'FUERA' concatenado con un pipe |
            estado_inicial = f"{puerta_seleccionada}|FUERA"
            cursor.execute("INSERT INTO socios (nombre, codigo_qr, estado) VALUES (%s, %s, %s)", (nombre, codigo_qr_generado, estado_inicial))
            db.commit()
            
            return redirect(url_for('ver_credencial', qr=codigo_qr_generado, nombre=nombre, puerta=puerta_seleccionada))
            
    except Exception as e:
        return f"Error interno: {str(e)}", 500
    finally:
        if db: db.close()
            
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Portal de Enrolamiento - Estadio</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .card {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }}
            h2 {{ color: #2c3e50; margin-top: 0; text-align: center; text-transform: uppercase; font-size: 20px; }}
            .form-group {{ margin-bottom: 20px; }}
            label {{ display: block; font-weight: bold; margin-bottom: 8px; color: #555; }}
            input[type="text"], select {{ width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; font-size: 14px; }}
            button {{ width: 100%; background-color: #27ae60; color: white; border: none; padding: 14px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 16px; transition: 0.3s; }}
            button:hover {{ background-color: #219653; }}
            .aforo-badge {{ text-align:center; background:#e3f2fd; color:#0d47a1; padding:8px; border-radius:6px; font-weight:bold; margin-bottom:20px; font-size:14px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Solicitud de Pase Digital</h2>
            <div class="aforo-badge">🎟️ Entradas Emitidas: {total_registrados} / {AFORO_MAXIMO}</div>
            <form action="/registro" method="POST">
                <div class="form-group">
                    <label>Nombre Completo:</label>
                    <input type="text" name="nombre" placeholder="Ej. Juan Pérez" required>
                </div>
                <div class="form-group">
                    <label>DNI o Número de Abono:</label>
                    <input type="text" name="identificador" placeholder="Ej. 12345678A" required>
                </div>
                <div class="form-group">
                    <label>Selecciona tu Puerta de Acceso:</label>
                    <select name="puerta">
                        <option value="Tribuna Norte">Tribuna Norte</option>
                        <option value="Gol Sur">Gol Sur</option>
                        <option value="Preferencia Este">Preferencia Este</option>
                    </select>
                </div>
                <button type="submit">Validar y Obtener QR</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.route("/credencial")
def ver_credencial():
    qr_data = request.args.get("qr")
    nombre = request.args.get("nombre")
    puerta = request.args.get("puerta")
    if not qr_data:
        return redirect(url_for('registro_usuario'))
        
    img = qrcode.make(qr_data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Mi Credencial - Estadio</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #2c3e50; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .ticket {{ background: white; padding: 30px; border-radius: 15px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.3); max-width: 350px; width: 100%; }}
            h3 {{ color: #27ae60; margin: 0 0 10px 0; text-transform: uppercase; }}
            .line {{ border-top: 2px dashed #ccc; margin: 20px 0; }}
            .code {{ font-family: monospace; background: #eee; padding: 8px; border-radius: 4px; font-size: 14px; display: inline-block; margin-top: 10px; }}
            .btn-volver {{ display: block; margin-top: 25px; color: #7f8c8d; text-decoration: none; font-size: 13px; font-weight: bold; }}
            .puerta-badge {{ background: #2980b9; color: white; padding: 5px 12px; border-radius: 20px; font-weight: bold; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="ticket">
            <h3>¡Registro Exitoso!</h3>
            <p style="margin: 5px 0; color: #555;">Titular: <strong>{nombre}</strong></p>
            <p style="margin: 10px 0;"><span class="puerta-badge">Puerta: {puerta}</span></p>
            <div class="line"></div>
            <img src="data:image/png;base64,{qr_base64}" alt="Código QR" width="220">
            <br>
            <span class="code">{qr_data}</span>
            <div class="line"></div>
            <p style="font-size: 12px; color: #e74c3c; font-weight: bold;">AVISO: Este código cuenta con sistema Anti-Passback.</p>
            <a href="/registro" class="btn-volver">← Registrar otro pase</a>
        </div>
    </body>
    </html>
    """

@app.route("/eliminar_socio/<int:id_socio>", methods=["POST"])
def eliminar_socio(id_socio):
    db, cursor = None, None
    try:
        db = MySQLdb.connect(**DB_CONFIG)
        cursor = db.cursor()
        cursor.execute("DELETE FROM socios WHERE id_socio = %s", (id_socio,))
        db.commit()
    except Exception as e:
        print(f"Error al eliminar: {e}")
    finally:
        if db: db.close()
    return redirect(url_for('dashboard'))

@app.route("/api/logs")
def api_logs():
    db, logs = None, []
    try:
        db = MySQLdb.connect(**DB_CONFIG)
        cursor = db.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT codigo_escaneado, puerta, DATE_FORMAT(fecha_acceso, '%Y-%m-%d %H:%i:%s') as fecha, resultado, motivo FROM registro_accesos ORDER BY fecha_acceso DESC LIMIT 10")
        logs = cursor.fetchall()
    except Exception as e:
        return jsonify([])
    finally:
        if db: db.close()
    return jsonify(logs)

@app.route("/dashboard")
def dashboard():
    db, socios_registrados = None, []
    try:
        db = MySQLdb.connect(**DB_CONFIG)
        cursor = db.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT id_socio, nombre, codigo_qr, estado FROM socios ORDER BY id_socio DESC")
        raw_socios = cursor.fetchall()
        
        # Formateamos los datos para separar la puerta del estado DENTRO/FUERA en la vista
        for s in raw_socios:
            partes = s["estado"].split("|")
            socios_registrados.append({
                "id_socio": s["id_socio"],
                "nombre": s["nombre"],
                "codigo_qr": s["codigo_qr"],
                "puerta": partes[0],
                "situacion": partes[1] if len(partes) > 1 else "FUERA"
            })
    except Exception as e:
        print(e)
    finally:
        if db: db.close()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Monitor General - Estadio</title>
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f6f9; color: #333; }
            h2 { color: #2c3e50; text-align: center; margin-bottom: 30px; text-transform: uppercase; letter-spacing: 1px; }
            .container { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 30px; }
            .panel { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }
            th { background-color: #2c3e50; color: white; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; }
            .concedido { background-color: #d4edda; color: #155724; font-weight: bold; padding: 5px 10px; border-radius: 4px; font-size: 12px; }
            .denegado { background-color: #f8d7da; color: #721c24; font-weight: bold; padding: 5px 10px; border-radius: 4px; font-size: 12px; }
            .badge-dentro { background-color: #2ecc71; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
            .badge-fuera { background-color: #e67e22; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
            .btn-borrar { background-color: #e74c3c; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px; }
            .btn-borrar:hover { background-color: #c0392b; }
            .meta-refresh { text-align: center; color: #7f8c8d; font-size: 12px; margin-top: 20px; }
        </style>
        <script>
            async function actualizarLogs() {
                try {
                    const response = await fetch('/api/logs');
                    const logs = await response.json();
                    const tbody = document.getElementById('logs-tbody');
                    let html = '';
                    logs.forEach(log => {
                        const claseResultado = log.resultado === 'concedido' ? 'concedido' : 'denegado';
                        html += `<tr>
                            <td><code>${log.codigo_escaneado}</code></td>
                            <td>${log.puerta}</td>
                            <td>${log.fecha}</td>
                            <td><span class="${claseResultado}">${log.resultado.toUpperCase()}</span></td>
                            <td>${log.motivo}</td>
                        </tr>`;
                    });
                    if(logs.length === 0) {
                        html = '<tr><td colspan="5" style="text-align:center; color:#999;">Sin actividad registrada en los tornos.</td></tr>';
                    }
                    tbody.innerHTML = html;
                } catch (e) { console.error(e); }
            }
            setInterval(actualizarLogs, 2000);
            window.onload = actualizarLogs;
        </script>
    </head>
    <body>
        <h2>MONITOR DE ENTRADAS AL ESTADIO EN TIEMPO REAL</h2>
        <div class="container">
            <div class="panel">
                <h3>Registro del Estado de los Tornos</h3>
                <table>
                    <thead>
                        <tr>
                            <th>QR Escaneado</th>
                            <th>Puerta del Torno</th>
                            <th>Fecha / Hora</th>
                            <th>Resultado Torno</th>
                            <th>Detalle del Sistema</th>
                        </tr>
                    </thead>
                    <tbody id="logs-tbody">
                    </tbody>
                </table>
                <p class="meta-refresh">🟢 Modo Escucha Activo: Sincronizando tráfico de espectadores asíncronamente...</p>
            </div>
            <div class="panel">
                <h3>Panel de Control: Códigos QR Emitidos (Aforo Activo)</h3>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Nombre Asistente</th>
                            <th>Código QR</th>
                            <th>Puerta Permitida</th>
                            <th>Situación Recinto</th>
                            <th>Acción</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for socio in socios_registrados %}
                        <tr>
                            <td>{{ socio.id_socio }}</td>
                            <td><strong>{{ socio.nombre }}</strong></td>
                            <td><code>{{ socio.codigo_qr }}</code></td>
                            <td>{{ socio.puerta }}</td>
                            <td>
                                {% if socio.situacion == 'DENTRO' %}
                                <span class="badge-dentro">DENTRO</span>
                                {% else %}
                                <span class="badge-fuera">FUERA</span>
                                {% endif %}
                            </td>
                            <td>
                                <form action="/eliminar_socio/{{ socio.id_socio }}" method="POST" style="margin:0;">
                                    <button type="submit" class="btn-borrar">Eliminar / Liberar</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="6" style="text-align:center; color:#999; padding:20px;">No hay ningún código QR generado todavía en el sistema.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, socios_registrados=socios_registrados)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
