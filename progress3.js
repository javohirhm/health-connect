const pptxgen = require("pptxgenjs");

let pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Javohir";
pres.title = "Progress Report — Week 3";

// Colors
const BG = "0A0A0A";
const CARD = "1C1C1E";
const CARD2 = "2C2C2E";
const GRAY = "86868B";
const GRAY2 = "636366";
const WHITE = "FFFFFF";
const RED = "FF453A";
const BLUE = "0A84FF";
const GREEN = "30D158";
const PURPLE = "BF5AF2";
const ORANGE = "FF9F0A";
const CYAN = "64D2FF";

function addBg(slide) {
  slide.background = { color: BG };
}

// ═══════════════════════════════════════════════════════════════
// SLIDE 1 — Title
// ═══════════════════════════════════════════════════════════════
let s1 = pres.addSlide();
addBg(s1);

// Top accent bar
s1.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: GREEN } });

s1.addText("Progress Report", {
  x: 0.8, y: 1.2, w: 8.4, h: 1.0,
  fontSize: 44, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});
s1.addText("Week 3 — Backend, ML Integration & Server Deployment", {
  x: 0.8, y: 2.1, w: 8.4, h: 0.6,
  fontSize: 20, fontFace: "Arial", color: GRAY, margin: 0,
});

// Info cards row
const infoCards = [
  { label: "Backend", value: "FastAPI 2.0", color: BLUE },
  { label: "ML Models", value: "3 Active", color: PURPLE },
  { label: "Endpoints", value: "25+", color: GREEN },
  { label: "Status", value: "Production Ready", color: ORANGE },
];
infoCards.forEach((c, i) => {
  const cx = 0.8 + i * 2.2;
  s1.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: cx, y: 3.4, w: 2.0, h: 1.2, fill: { color: CARD }, rectRadius: 0.12,
  });
  s1.addText(c.label, { x: cx, y: 3.5, w: 2.0, h: 0.35, fontSize: 11, color: GRAY, align: "center", margin: 0 });
  s1.addText(c.value, { x: cx, y: 3.85, w: 2.0, h: 0.55, fontSize: 16, color: c.color, bold: true, align: "center", margin: 0 });
});

s1.addText("Health Connect Ecosystem", {
  x: 0.8, y: 5.0, w: 8.4, h: 0.3, fontSize: 11, color: GRAY2, margin: 0,
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 2 — What We Built This Week
// ═══════════════════════════════════════════════════════════════
let s2 = pres.addSlide();
addBg(s2);
s2.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: BLUE } });

s2.addText("What We Built This Week", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});

const features = [
  { icon: "🗄️", title: "PostgreSQL Support", desc: "Switched from SQLite to production PostgreSQL with connection pooling", color: BLUE },
  { icon: "🤖", title: "ML Arrhythmia Detection", desc: "XGBoost (98.18%) & SVM (98.24%) classify ECG beats into 5 AAMI classes", color: PURPLE },
  { icon: "📊", title: "Web Dashboard", desc: "Real-time browser dashboard with ECG waveform, HR charts, sensor distribution", color: GREEN },
  { icon: "📄", title: "Health Reports & CSV Export", desc: "Downloadable health reports and CSV data export for all sensors", color: ORANGE },
  { icon: "🔒", title: "Security Fixes", desc: "SQL injection patched, environment config, table allowlist validation", color: RED },
  { icon: "🌐", title: "Server Deployment Ready", desc: "systemd service, Nginx reverse proxy, HTTPS with Let's Encrypt", color: CYAN },
];

features.forEach((f, i) => {
  const col = i % 2;
  const row = Math.floor(i / 2);
  const fx = 0.8 + col * 4.4;
  const fy = 1.3 + row * 1.35;

  s2.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: fx, y: fy, w: 4.1, h: 1.15, fill: { color: CARD }, rectRadius: 0.1,
  });
  // Color dot
  s2.addShape(pres.shapes.OVAL, { x: fx + 0.2, y: fy + 0.2, w: 0.22, h: 0.22, fill: { color: f.color } });
  s2.addText(f.title, { x: fx + 0.55, y: fy + 0.12, w: 3.3, h: 0.35, fontSize: 14, color: WHITE, bold: true, margin: 0 });
  s2.addText(f.desc, { x: fx + 0.55, y: fy + 0.48, w: 3.3, h: 0.55, fontSize: 10.5, color: GRAY, margin: 0 });
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 3 — Backend Architecture
// ═══════════════════════════════════════════════════════════════
let s3 = pres.addSlide();
addBg(s3);
s3.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: PURPLE } });

s3.addText("Backend Architecture", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});
s3.addText("FastAPI + PostgreSQL + ML Pipeline", {
  x: 0.8, y: 0.85, w: 8, h: 0.35, fontSize: 14, color: GRAY, margin: 0,
});

// Architecture flow boxes
const archBoxes = [
  { label: "Galaxy Watch 5", sub: "Samsung Health\nSensor SDK", color: CYAN, x: 0.3 },
  { label: "Android Phone", sub: "Material3\nDark Theme", color: BLUE, x: 2.4 },
  { label: "FastAPI", sub: "REST API\n25+ Endpoints", color: GREEN, x: 4.5 },
  { label: "PostgreSQL", sub: "Production DB\nConnection Pool", color: ORANGE, x: 6.6 },
  { label: "ML Models", sub: "XGBoost, SVM\nArrhythmia Detection", color: PURPLE, x: 8.2 },
];

archBoxes.forEach((b) => {
  s3.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: b.x, y: 1.55, w: 1.65, h: 1.3, fill: { color: CARD }, rectRadius: 0.1,
  });
  // Top color bar
  s3.addShape(pres.shapes.RECTANGLE, { x: b.x, y: 1.55, w: 1.65, h: 0.05, fill: { color: b.color } });
  s3.addText(b.label, { x: b.x, y: 1.7, w: 1.65, h: 0.35, fontSize: 11, color: b.color, bold: true, align: "center", margin: 0 });
  s3.addText(b.sub, { x: b.x, y: 2.05, w: 1.65, h: 0.6, fontSize: 9, color: GRAY, align: "center", margin: 0 });
});

// Arrows between boxes
[1.95, 4.05, 6.15, 7.85].forEach(ax => {
  s3.addText("→", { x: ax, y: 1.85, w: 0.45, h: 0.4, fontSize: 20, color: GRAY2, align: "center", margin: 0 });
});

// API Endpoints summary
s3.addText("API Endpoints", {
  x: 0.8, y: 3.2, w: 4, h: 0.4, fontSize: 16, color: WHITE, bold: true, margin: 0,
});

const endpoints = [
  { method: "POST", path: "/api/v1/sync", desc: "Sync Health Connect data", color: GREEN },
  { method: "POST", path: "/api/v2/watch/sync", desc: "Sync watch sensor data", color: GREEN },
  { method: "POST", path: "/ecg/{id}/classify", desc: "Run ML arrhythmia detection", color: PURPLE },
  { method: "GET", path: "/api/v2/watch/{id}/report", desc: "Generate health report", color: ORANGE },
  { method: "GET", path: "/dashboard", desc: "Web dashboard", color: BLUE },
  { method: "GET", path: "/export/csv", desc: "Download data as CSV", color: CYAN },
];

endpoints.forEach((e, i) => {
  const ey = 3.7 + i * 0.3;
  s3.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.8, y: ey, w: 0.55, h: 0.22, fill: { color: e.color }, rectRadius: 0.04,
  });
  s3.addText(e.method, { x: 0.8, y: ey, w: 0.55, h: 0.22, fontSize: 8, color: BG, bold: true, align: "center", margin: 0 });
  s3.addText(e.path, { x: 1.45, y: ey, w: 2.8, h: 0.22, fontSize: 9, fontFace: "Courier New", color: WHITE, margin: 0 });
  s3.addText(e.desc, { x: 4.4, y: ey, w: 3, h: 0.22, fontSize: 9, color: GRAY, margin: 0 });
});

// Tech stack on right
s3.addText("Tech Stack", {
  x: 5.8, y: 3.2, w: 4, h: 0.4, fontSize: 16, color: WHITE, bold: true, margin: 0,
});

const stack = [
  { name: "FastAPI", ver: "v0.115", color: GREEN },
  { name: "PostgreSQL", ver: "Production DB", color: ORANGE },
  { name: "TensorFlow", ver: "v2.20", color: PURPLE },
  { name: "XGBoost", ver: "v2.1.4", color: BLUE },
  { name: "scikit-learn", ver: "v1.6", color: CYAN },
  { name: "Uvicorn", ver: "ASGI Server", color: RED },
];

stack.forEach((s, i) => {
  const sy = 3.7 + i * 0.3;
  s3.addShape(pres.shapes.OVAL, { x: 5.8, y: sy + 0.04, w: 0.14, h: 0.14, fill: { color: s.color } });
  s3.addText(s.name, { x: 6.05, y: sy, w: 1.8, h: 0.22, fontSize: 10, color: WHITE, bold: true, margin: 0 });
  s3.addText(s.ver, { x: 7.8, y: sy, w: 1.8, h: 0.22, fontSize: 9, color: GRAY, margin: 0 });
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 4 — ML Arrhythmia Detection
// ═══════════════════════════════════════════════════════════════
let s4 = pres.addSlide();
addBg(s4);
s4.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: RED } });

s4.addText("ECG Arrhythmia Detection", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});
s4.addText("ML models classify each heartbeat from Galaxy Watch ECG recordings", {
  x: 0.8, y: 0.85, w: 8, h: 0.35, fontSize: 14, color: GRAY, margin: 0,
});

// Pipeline steps
const pipeline = [
  { num: "1", title: "Record", desc: "500Hz ECG\nfrom watch", color: CYAN },
  { num: "2", title: "Filter", desc: "Bandpass\n0.5-45 Hz", color: BLUE },
  { num: "3", title: "Resample", desc: "500Hz →\n360Hz", color: GREEN },
  { num: "4", title: "Detect", desc: "R-peak\ndetection", color: ORANGE },
  { num: "5", title: "Segment", desc: "360-sample\nbeats", color: PURPLE },
  { num: "6", title: "Classify", desc: "5 AAMI\nclasses", color: RED },
];

pipeline.forEach((p, i) => {
  const px = 0.4 + i * 1.58;
  s4.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: px, y: 1.5, w: 1.35, h: 1.2, fill: { color: CARD }, rectRadius: 0.1,
  });
  // Number circle
  s4.addShape(pres.shapes.OVAL, { x: px + 0.48, y: 1.58, w: 0.4, h: 0.4, fill: { color: p.color } });
  s4.addText(p.num, { x: px + 0.48, y: 1.58, w: 0.4, h: 0.4, fontSize: 14, color: BG, bold: true, align: "center", valign: "middle", margin: 0 });
  s4.addText(p.title, { x: px, y: 2.05, w: 1.35, h: 0.25, fontSize: 11, color: WHITE, bold: true, align: "center", margin: 0 });
  s4.addText(p.desc, { x: px, y: 2.3, w: 1.35, h: 0.35, fontSize: 9, color: GRAY, align: "center", margin: 0 });
});

// Arrows
[1.75, 3.33, 4.91, 6.49, 8.07].forEach(ax => {
  s4.addText("›", { x: ax, y: 1.8, w: 0.23, h: 0.4, fontSize: 22, color: GRAY2, align: "center", margin: 0 });
});

// Classification results
s4.addText("5 AAMI Beat Classes", {
  x: 0.8, y: 3.1, w: 4, h: 0.4, fontSize: 16, color: WHITE, bold: true, margin: 0,
});

const classes = [
  { code: "N", name: "Normal", desc: "Healthy heartbeat", color: GREEN },
  { code: "S", name: "Supraventricular", desc: "Atrial arrhythmia", color: BLUE },
  { code: "V", name: "Ventricular", desc: "Dangerous arrhythmia", color: RED },
  { code: "F", name: "Fusion", desc: "Mixed beat", color: ORANGE },
  { code: "Q", name: "Unknown/Paced", desc: "Pacemaker beat", color: PURPLE },
];

classes.forEach((c, i) => {
  const cy = 3.6 + i * 0.36;
  s4.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.8, y: cy, w: 0.35, h: 0.28, fill: { color: c.color }, rectRadius: 0.05,
  });
  s4.addText(c.code, { x: 0.8, y: cy, w: 0.35, h: 0.28, fontSize: 12, color: BG, bold: true, align: "center", valign: "middle", margin: 0 });
  s4.addText(c.name, { x: 1.25, y: cy, w: 2, h: 0.28, fontSize: 11, color: WHITE, bold: true, margin: 0 });
  s4.addText(c.desc, { x: 3.3, y: cy, w: 2, h: 0.28, fontSize: 10, color: GRAY, margin: 0 });
});

// Model results on right
s4.addText("Model Accuracy", {
  x: 5.8, y: 3.1, w: 4, h: 0.4, fontSize: 16, color: WHITE, bold: true, margin: 0,
});

const models = [
  { name: "XGBoost", acc: "98.18%", status: "Active", color: GREEN },
  { name: "SVM (RBF)", acc: "98.24%", status: "Active", color: GREEN },
  { name: "1D-CNN", acc: "98.28%", status: "Pending*", color: ORANGE },
];

models.forEach((m, i) => {
  const my = 3.6 + i * 0.55;
  s4.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.8, y: my, w: 3.8, h: 0.45, fill: { color: CARD }, rectRadius: 0.08,
  });
  s4.addText(m.name, { x: 6.0, y: my + 0.02, w: 1.5, h: 0.2, fontSize: 12, color: WHITE, bold: true, margin: 0 });
  s4.addText(m.acc, { x: 7.6, y: my + 0.02, w: 0.9, h: 0.2, fontSize: 14, color: m.color, bold: true, align: "center", margin: 0 });
  s4.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 8.6, y: my + 0.08, w: 0.8, h: 0.22, fill: { color: m.status === "Active" ? "0b3d1a" : "3d2a0b" }, rectRadius: 0.04,
  });
  s4.addText(m.status, { x: 8.6, y: my + 0.08, w: 0.8, h: 0.22, fontSize: 8, color: m.color, align: "center", valign: "middle", margin: 0 });
});

s4.addText("*1D-CNN requires Keras version alignment — retraining planned", {
  x: 5.8, y: 5.2, w: 3.8, h: 0.25, fontSize: 8, color: GRAY2, margin: 0,
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 5 — Web Dashboard & Reports
// ═══════════════════════════════════════════════════════════════
let s5 = pres.addSlide();
addBg(s5);
s5.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: CYAN } });

s5.addText("Web Dashboard & Health Reports", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});
s5.addText("Real-time visualization accessible from any browser", {
  x: 0.8, y: 0.85, w: 8, h: 0.35, fontSize: 14, color: GRAY, margin: 0,
});

// Dashboard features - left side
s5.addText("Dashboard Features", {
  x: 0.8, y: 1.5, w: 4, h: 0.4, fontSize: 16, color: CYAN, bold: true, margin: 0,
});

const dashFeatures = [
  "Live ECG waveform with Chart.js rendering",
  "Heart rate history graph (last 50 readings)",
  "Sensor data distribution (doughnut chart)",
  "One-click ECG classification with results",
  "Vital signs cards (HR, SpO2, Temp, Records)",
  "Auto-refresh every 30 seconds",
];

dashFeatures.forEach((f, i) => {
  const dy = 2.05 + i * 0.32;
  s5.addShape(pres.shapes.OVAL, { x: 1.0, y: dy + 0.06, w: 0.12, h: 0.12, fill: { color: CYAN } });
  s5.addText(f, { x: 1.25, y: dy, w: 3.8, h: 0.28, fontSize: 11, color: WHITE, margin: 0 });
});

// Reports & Export - right side
s5.addText("Reports & Export", {
  x: 5.5, y: 1.5, w: 4, h: 0.4, fontSize: 16, color: ORANGE, bold: true, margin: 0,
});

const reportFeatures = [
  { title: "Health Report", desc: "Full HTML report — printable as PDF from browser", color: ORANGE },
  { title: "CSV Export", desc: "Download any sensor data as spreadsheet", color: GREEN },
  { title: "ECG Export", desc: "Individual ECG as time-series CSV", color: RED },
  { title: "Device Export", desc: "All Health Connect data (HR, steps, sleep)", color: BLUE },
];

reportFeatures.forEach((r, i) => {
  const ry = 2.05 + i * 0.65;
  s5.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 5.5, y: ry, w: 3.8, h: 0.55, fill: { color: CARD }, rectRadius: 0.08,
  });
  s5.addShape(pres.shapes.OVAL, { x: 5.7, y: ry + 0.15, w: 0.18, h: 0.18, fill: { color: r.color } });
  s5.addText(r.title, { x: 6.0, y: ry + 0.05, w: 3.1, h: 0.22, fontSize: 12, color: WHITE, bold: true, margin: 0 });
  s5.addText(r.desc, { x: 6.0, y: ry + 0.28, w: 3.1, h: 0.2, fontSize: 9.5, color: GRAY, margin: 0 });
});

// Screenshot placeholder
s5.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 0.8, y: 4.15, w: 8.4, h: 1.2, fill: { color: CARD }, rectRadius: 0.12,
  line: { color: CARD2, width: 1, dashType: "dash" },
});
s5.addText("Insert: Dashboard Screenshot (localhost:8000/dashboard)", {
  x: 0.8, y: 4.55, w: 8.4, h: 0.4, fontSize: 12, color: GRAY2, align: "center", margin: 0,
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 6 — Mobile App Design
// ═══════════════════════════════════════════════════════════════
let s6 = pres.addSlide();
addBg(s6);
s6.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: GREEN } });

s6.addText("Mobile App — Dark Theme Redesign", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});
s6.addText("Apple Fitness-inspired UI with iOS system colors", {
  x: 0.8, y: 0.85, w: 8, h: 0.35, fontSize: 14, color: GRAY, margin: 0,
});

// Phone mockup placeholders
const phones = [
  { title: "Main Screen", x: 0.5 },
  { title: "Dashboard", x: 3.5 },
  { title: "ECG Viewer", x: 6.5 },
];

phones.forEach(p => {
  // Phone frame
  s6.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: p.x, y: 1.5, w: 2.6, h: 3.5, fill: { color: CARD },
    rectRadius: 0.15, line: { color: CARD2, width: 1, dashType: "dash" },
  });
  s6.addText("Insert: " + p.title + " Screenshot", {
    x: p.x, y: 2.9, w: 2.6, h: 0.5, fontSize: 10, color: GRAY2, align: "center", margin: 0,
  });
  s6.addText(p.title, { x: p.x, y: 5.1, w: 2.6, h: 0.3, fontSize: 12, color: WHITE, bold: true, align: "center", margin: 0 });
});

// Design highlights
const designPoints = [
  { label: "Background", value: "#000000", color: WHITE },
  { label: "Cards", value: "#1C1C1E", color: GRAY },
  { label: "HR Red", value: "#FF453A", color: RED },
  { label: "Steps Blue", value: "#0A84FF", color: BLUE },
  { label: "Active Green", value: "#30D158", color: GREEN },
];

designPoints.forEach((d, i) => {
  const dx = 0.5 + i * 1.85;
  s6.addShape(pres.shapes.OVAL, { x: dx + 0.1, y: 5.45, w: 0.14, h: 0.14, fill: { color: d.color } });
  s6.addText(d.label + "  " + d.value, {
    x: dx + 0.3, y: 5.4, w: 1.6, h: 0.25, fontSize: 8.5, color: GRAY, margin: 0,
  });
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 7 — Server Deployment
// ═══════════════════════════════════════════════════════════════
let s7 = pres.addSlide();
addBg(s7);
s7.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: ORANGE } });

s7.addText("Server Deployment Plan", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});
s7.addText("Moving from localhost to production server with HTTPS", {
  x: 0.8, y: 0.85, w: 8, h: 0.35, fontSize: 14, color: GRAY, margin: 0,
});

// Before vs After
// Before
s7.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 0.5, y: 1.5, w: 4.3, h: 2.2, fill: { color: CARD }, rectRadius: 0.12,
});
s7.addText("Before (Development)", {
  x: 0.7, y: 1.6, w: 3.9, h: 0.35, fontSize: 15, color: RED, bold: true, margin: 0,
});

const beforeItems = [
  "SQLite local database",
  "localhost:8000 only",
  "No authentication",
  "Home WiFi only",
  "Manual restart on crash",
];
beforeItems.forEach((b, i) => {
  const by = 2.05 + i * 0.3;
  s7.addText("✕", { x: 0.8, y: by, w: 0.3, h: 0.25, fontSize: 12, color: RED, margin: 0 });
  s7.addText(b, { x: 1.15, y: by, w: 3.4, h: 0.25, fontSize: 11, color: GRAY, margin: 0 });
});

// After
s7.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 5.2, y: 1.5, w: 4.3, h: 2.2, fill: { color: CARD }, rectRadius: 0.12,
});
s7.addText("After (Production)", {
  x: 5.4, y: 1.6, w: 3.9, h: 0.35, fontSize: 15, color: GREEN, bold: true, margin: 0,
});

const afterItems = [
  "PostgreSQL with connection pooling",
  "HTTPS via Let's Encrypt + domain",
  "API key authentication",
  "Accessible from anywhere",
  "systemd auto-restart service",
];
afterItems.forEach((a, i) => {
  const ay = 2.05 + i * 0.3;
  s7.addText("✓", { x: 5.5, y: ay, w: 0.3, h: 0.25, fontSize: 12, color: GREEN, margin: 0 });
  s7.addText(a, { x: 5.85, y: ay, w: 3.4, h: 0.25, fontSize: 11, color: WHITE, margin: 0 });
});

// Deployment steps
s7.addText("Deployment Stack", {
  x: 0.8, y: 4.05, w: 4, h: 0.35, fontSize: 16, color: WHITE, bold: true, margin: 0,
});

const deployStack = [
  { name: "Nginx", role: "Reverse proxy + SSL termination", color: GREEN },
  { name: "Gunicorn/Uvicorn", role: "ASGI server (4 workers)", color: BLUE },
  { name: "PostgreSQL", role: "Production database", color: ORANGE },
  { name: "systemd", role: "Process management + auto-restart", color: PURPLE },
  { name: "Let's Encrypt", role: "Free HTTPS certificates", color: CYAN },
];

deployStack.forEach((d, i) => {
  const dy = 4.5 + i * 0.22;
  s7.addShape(pres.shapes.OVAL, { x: 0.8, y: dy + 0.04, w: 0.12, h: 0.12, fill: { color: d.color } });
  s7.addText(d.name, { x: 1.05, y: dy, w: 2, h: 0.2, fontSize: 10, color: WHITE, bold: true, margin: 0 });
  s7.addText(d.role, { x: 3.1, y: dy, w: 3, h: 0.2, fontSize: 9.5, color: GRAY, margin: 0 });
});

// ═══════════════════════════════════════════════════════════════
// SLIDE 8 — Next Steps
// ═══════════════════════════════════════════════════════════════
let s8 = pres.addSlide();
addBg(s8);
s8.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: GREEN } });

s8.addText("Next Steps", {
  x: 0.8, y: 0.3, w: 8, h: 0.7, fontSize: 32, fontFace: "Arial", color: WHITE, bold: true, margin: 0,
});

const nextSteps = [
  { title: "Deploy to Production Server", desc: "Set up PostgreSQL, Nginx, HTTPS, and systemd on VPS", status: "This Week", color: GREEN },
  { title: "Real-time Alerts", desc: "Push notifications for abnormal HR or arrhythmia detection", status: "Planned", color: ORANGE },
  { title: "Retrain 1D-CNN Model", desc: "Fix Keras compatibility — achieve 98.28% accuracy on server", status: "Planned", color: PURPLE },
  { title: "WebSocket Live Streaming", desc: "Real-time data push from watch to web dashboard", status: "Planned", color: CYAN },
  { title: "Multi-user Support", desc: "JWT authentication, user accounts, data isolation", status: "Future", color: BLUE },
];

nextSteps.forEach((n, i) => {
  const ny = 1.3 + i * 0.8;
  s8.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.8, y: ny, w: 8.4, h: 0.65, fill: { color: CARD }, rectRadius: 0.1,
  });
  // Left color bar
  s8.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: ny, w: 0.06, h: 0.65, fill: { color: n.color } });
  s8.addText(n.title, { x: 1.1, y: ny + 0.06, w: 5, h: 0.25, fontSize: 14, color: WHITE, bold: true, margin: 0 });
  s8.addText(n.desc, { x: 1.1, y: ny + 0.32, w: 5, h: 0.25, fontSize: 10.5, color: GRAY, margin: 0 });
  // Status badge
  s8.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 7.8, y: ny + 0.18, w: 1.2, h: 0.28,
    fill: { color: n.status === "This Week" ? "0b3d1a" : n.status === "Planned" ? "3d2a0b" : CARD2 },
    rectRadius: 0.05,
  });
  s8.addText(n.status, {
    x: 7.8, y: ny + 0.18, w: 1.2, h: 0.28,
    fontSize: 9, color: n.status === "This Week" ? GREEN : n.status === "Planned" ? ORANGE : GRAY,
    align: "center", valign: "middle", bold: true, margin: 0,
  });
});

// Footer
s8.addText("Thank You", {
  x: 0.8, y: 5.1, w: 8.4, h: 0.35,
  fontSize: 12, color: GRAY2, margin: 0,
});

// Save
pres.writeFile({ fileName: "/Users/javohir/connect/Progress_Week3.pptx" })
  .then(() => console.log("Saved: /Users/javohir/connect/Progress_Week3.pptx"))
  .catch(err => console.error(err));
