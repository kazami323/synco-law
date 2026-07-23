import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const apiUrl = (process.argv[2] || "https://api.synco.law").replace(/\/$/, "");

if (!apiUrl.startsWith("https://")) {
  throw new Error("The production API URL must use HTTPS");
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} exited with code ${result.status}`);
  }
}

const outputRoot = join(root, "deploy-output");
const packageDir = join(outputRoot, "ahost-frontend");
const archive = join(outputRoot, "synco-ahost-frontend.tar.gz");
const image = "synco-ahost-frontend-build";
const container = `synco-ahost-export-${process.pid}`;

rmSync(outputRoot, { recursive: true, force: true });
mkdirSync(packageDir, { recursive: true });

run("docker", [
  "build",
  "--build-arg",
  `NEXT_PUBLIC_API_URL=${apiUrl}`,
  "--build-arg",
  `NEXT_PUBLIC_UPLOAD_API_URL=${apiUrl}`,
  "-t",
  image,
  ".",
]);

try {
  run("docker", ["create", "--name", container, image]);
  run("docker", ["cp", `${container}:/app/.`, packageDir]);
} finally {
  spawnSync("docker", ["rm", "-f", container], {
    cwd: root,
    stdio: "ignore",
  });
}

writeFileSync(
  join(packageDir, "DEPLOY.txt"),
  `SynCo frontend\nAPI: ${apiUrl}\nStart file: server.js\n`,
  "utf8",
);

// Пути передаём относительными и запускаем из outputRoot: на Windows GNU tar
// принимает абсолютный "C:\...tar.gz" за host:path (буква диска до двоеточия =
// "хост") и падает с "Cannot connect to C". Относительные имена этого избегают.
run("tar", ["-czf", "synco-ahost-frontend.tar.gz", "-C", "ahost-frontend", "."], {
  cwd: outputRoot,
});

console.log(`\nAhost package: ${archive}`);
