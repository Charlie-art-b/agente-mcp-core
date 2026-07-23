-- Esquema del dominio de reservaciones de un negocio pequeño
-- (salón de belleza, restaurante, consultorio, etc.)
--
-- ⚠️  ESTE ARCHIVO NO SE EJECUTA. Es documentación de referencia.
--
-- Las tablas reales las crea SQLAlchemy desde app/db/models.py, que es la
-- única fuente de verdad del esquema. Antes este archivo se montaba en
-- /docker-entrypoint-initdb.d/ y Postgres lo ejecutaba al crear la base:
-- el esquema quedaba definido en dos lugares y se desincronizaron
-- (`hora_inicio` era TIME acá y VARCHAR(5) en los modelos), lo que solo
-- explotaba al insertar datos reales -- nunca en los tests, porque en
-- SQLite las tablas sí las crea SQLAlchemy.
--
-- Si cambiás algo en models.py, actualizá este archivo para que siga
-- sirviendo como referencia, o borralo.

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
    -- VARCHAR(5) y no TIME: los modelos las manejan como "09:00", y así
    -- viajan directo a JSON sin conversión cuando el agente las consulta.
    hora_inicio VARCHAR(5) NOT NULL,
    hora_fin VARCHAR(5) NOT NULL,
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
