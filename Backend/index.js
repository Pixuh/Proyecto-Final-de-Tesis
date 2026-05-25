const express = require("express");
const cors = require("cors");
const { Pool } = require("pg");

const app = express();
const port = process.env.PORT || 3001;

const pool = new Pool({
  host: process.env.DB_HOST || "localhost",
  port: Number(process.env.DB_PORT || 5432),
  database: process.env.DB_NAME || "proyecto_tesis",
  user: process.env.DB_USER || "postgres",
  password: process.env.DB_PASSWORD || "postgres",
});

app.use(cors());
app.use(express.json());

async function initDatabase() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS count_events (
      id SERIAL PRIMARY KEY,
      camera_id TEXT NOT NULL DEFAULT 'main_camera',
      direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
      quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
      occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
  `);
}

app.get("/", (req, res) => {
  res.json({
    message: "Backend funcionando correctamente",
    service: "people-counting-api",
  });
});

app.get("/health", async (req, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ status: "ok", database: "connected" });
  } catch (error) {
    res.status(503).json({ status: "error", database: "unavailable" });
  }
});

app.post("/counts/events", async (req, res) => {
  const { cameraId = "main_camera", direction, quantity = 1, metadata = {} } = req.body;

  if (!["in", "out"].includes(direction)) {
    return res.status(400).json({ error: "direction debe ser 'in' o 'out'" });
  }

  const parsedQuantity = Number(quantity);
  if (!Number.isInteger(parsedQuantity) || parsedQuantity <= 0) {
    return res.status(400).json({ error: "quantity debe ser un entero mayor a 0" });
  }

  const result = await pool.query(
    `INSERT INTO count_events (camera_id, direction, quantity, metadata)
     VALUES ($1, $2, $3, $4)
     RETURNING id, camera_id, direction, quantity, occurred_at, metadata`,
    [cameraId, direction, parsedQuantity, metadata]
  );

  res.status(201).json(result.rows[0]);
});

app.get("/counts/events", async (req, res) => {
  const limit = Math.min(Number(req.query.limit || 20), 100);
  const result = await pool.query(
    `SELECT id, camera_id, direction, quantity, occurred_at, metadata
     FROM count_events
     ORDER BY occurred_at DESC
     LIMIT $1`,
    [limit]
  );

  res.json(result.rows);
});

app.get("/counts/summary", async (req, res) => {
  const result = await pool.query(`
    SELECT
      COALESCE(SUM(quantity) FILTER (WHERE direction = 'in'), 0)::int AS total_in,
      COALESCE(SUM(quantity) FILTER (WHERE direction = 'out'), 0)::int AS total_out,
      (
        COALESCE(SUM(quantity) FILTER (WHERE direction = 'in'), 0) -
        COALESCE(SUM(quantity) FILTER (WHERE direction = 'out'), 0)
      )::int AS current_inside,
      COUNT(*)::int AS events
    FROM count_events;
  `);

  res.json(result.rows[0]);
});

initDatabase()
  .then(() => {
    app.listen(port, () => {
      console.log(`Backend escuchando en puerto ${port}`);
    });
  })
  .catch((error) => {
    console.error("No se pudo inicializar la base de datos", error);
    process.exit(1);
  });
