CREATE TABLE IF NOY EXISTS socio (
    id_socio INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    codigo_qr VARCHAR(255) UNIQUE NOT NULL,
    estado ENUM('activo', 'inactivo') DEFAULT 'activo',
    fecha_alta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS registro_accesos (
    id_acceso INT AUTO_INCREMENT PRIMARY KEY,
    id_socio INT NULL,
    codigo_escaneado VARCHAR(255) NOT NULL,
    fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    puerta VARCHAR(50) NOT NULL,
    resultado ENUM('concedido','denegado') NOT NULL,
    motivo VARCHAR(255) NULL,
    FOREIGN KEY (id_socio) REFERENCES socios(id_socios) ON DELETE SET NULL
);

INSERT INTO socios (nombre, codigo_qr, estado) VALUES
('Jose Garcia','QR_SOCIO_001','activo'),
('Andres Martinez','QR_SOCIO_002','inactivo'),
('Carlos Lopez','QR_SOCIO_003','activo');
