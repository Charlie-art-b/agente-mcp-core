-- Esquema inicial para el dominio de reservaciones de un negocio pequeño
-- (salón de belleza, restaurante, consultorio, etc.)

CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    telefono VARCHAR(30) UNIQUE,
    email VARCHAR(150),
    creado_en TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS servicios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    duracion_minutos INT NOT NULL,
    precio NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS horarios_disponibles (
    id SERIAL PRIMARY KEY,
    servicio_id INT REFERENCES servicios(id),
    fecha DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    disponible BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS reservaciones (
    id SERIAL PRIMARY KEY,
    cliente_id INT REFERENCES clientes(id),
    servicio_id INT REFERENCES servicios(id),
    horario_id INT REFERENCES horarios_disponibles(id),
    estado VARCHAR(30) DEFAULT 'confirmada', -- confirmada | cancelada | completada
    creado_en TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tickets_escalados (
    id SERIAL PRIMARY KEY,
    cliente_id INT REFERENCES clientes(id),
    motivo TEXT NOT NULL,
    estado VARCHAR(30) DEFAULT 'abierto', -- abierto | en_proceso | cerrado
    creado_en TIMESTAMP DEFAULT NOW()
);

-- Tabla de logging/observabilidad: cada interacción del agente queda registrada
CREATE TABLE IF NOT EXISTS interacciones_log (
    id SERIAL PRIMARY KEY,
    cliente_id INT REFERENCES clientes(id),
    mensaje_usuario TEXT NOT NULL,
    tool_llamada VARCHAR(100),
    tool_input JSONB,
    tool_output JSONB,
    respuesta_agente TEXT,
    tokens_input INT,
    tokens_output INT,
    costo_usd NUMERIC(10, 6),
    latencia_ms INT,
    creado_en TIMESTAMP DEFAULT NOW()
);
