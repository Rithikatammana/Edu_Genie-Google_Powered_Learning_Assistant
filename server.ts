import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { spawn } from "child_process";
import dotenv from "dotenv";
import fs from "fs";

// Load .env.local first (takes priority), then fall back to .env
if (fs.existsSync(".env.local")) {
  dotenv.config({ path: ".env.local" });
} else {
  dotenv.config();
}

const app = express();
app.use(express.json({ limit: "10mb" }));

// Spawn the Python backend API server
console.log("[EduGenie Launcher] Starting Python API backend...");
const pythonProcess = spawn(process.platform === "win32" ? "python" : "python3", ["app.py"], {
  env: { ...process.env }
});

pythonProcess.stdout.on("data", (data) => {
  console.log(`[Python API Server] ${data.toString().trim()}`);
});

pythonProcess.stderr.on("data", (data) => {
  console.error(`[Python API Server Error] ${data.toString().trim()}`);
});

pythonProcess.on("close", (code) => {
  console.warn(`[EduGenie Launcher] Python API backend process exited with code ${code}`);
});

process.on("exit", () => {
  console.log("[EduGenie Launcher] Parent process exiting, terminating Python API backend...");
  pythonProcess.kill();
});

// Helper to proxy requests to the Python API server on port 5000
async function proxyToPython(apiPath: string, reqBody: any, res: any) {
  try {
    // Wait briefly if Python server is still starting up
    const response = await fetch(`http://127.0.0.1:5000${apiPath}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(reqBody)
    });

    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error: any) {
    console.error(`[Proxy Error] Failed to contact Python backend at ${apiPath}:`, error.message);
    res.status(503).json({
      error: "The Python AI service is starting up or temporarily unavailable. Please try again in a few seconds."
    });
  }
}

// 1. Intelligent Question Answering Route
app.post("/api/qa", (req, res) => {
  proxyToPython("/api/qa", req.body, res);
});

// 2. Simplified Concept Explanations Route
app.post("/api/explain", (req, res) => {
  proxyToPython("/api/explain", req.body, res);
});

// 3. AI-Powered Quiz Generation Route
app.post("/api/quiz", (req, res) => {
  proxyToPython("/api/quiz", req.body, res);
});

// 4. Educational Text Summarization Route
app.post("/api/summarize", (req, res) => {
  proxyToPython("/api/summarize", req.body, res);
});

// 5. Personalized Learning Path Recommendations Route
app.post("/api/learning-path", (req, res) => {
  proxyToPython("/api/learning-path", req.body, res);
});

// 6. Auth Routes
app.post("/api/auth/register", (req, res) => {
  proxyToPython("/api/auth/register", req.body, res);
});

app.post("/api/auth/login", (req, res) => {
  proxyToPython("/api/auth/login", req.body, res);
});

// Integrate Vite Middleware
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const PORT = 3000;
  app.listen(PORT, "0.0.0.0", () => {
    console.log(`EduGenie proxy server running on http://localhost:${PORT}`);
  });
}

startServer();
