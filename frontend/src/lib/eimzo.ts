/**
 * Интеграция с E-IMZO — государственной системой ЭЦП Узбекистана.
 *
 * Установленный клиент E-IMZO (e-imzo.uz) поднимает локальный WebSocket
 * wss://127.0.0.1:64443/service/cryptapi (протокол CAPIWS). Сайт общается
 * с ним напрямую из браузера: список ключей пользователя → загрузка ключа
 * (пароль спрашивает сам клиент E-IMZO) → создание подписи PKCS#7.
 */

const CAPIWS_URL = "wss://127.0.0.1:64443/service/cryptapi";

// Публичные тестовые API-ключи E-IMZO для локальной разработки (из
// официальной документации). Для боевого домена зарегистрируйте свой ключ
// в НИЦ НТ и передайте пары "домен,ключ" через NEXT_PUBLIC_EIMZO_API_KEYS.
const DEFAULT_API_KEYS = [
  "localhost",
  "96D0C1491615C82B9A54D9989779DF825B690748224C2B04F500F370D51827CE2644D8D4A82C18184D73AB8530BB8ED537269603F61DB0D03D2104ABF789970B",
  "127.0.0.1",
  "A7BCFA5D490B351BE0754130DF03A068F855DB4333D43921125B9CF2670EF6A40370C646B90401955E1F7BC9CDBF59CE0B2C5467D820BE189C845D0B79CFC96F",
];

function apiKeys(): string[] {
  const env = process.env.NEXT_PUBLIC_EIMZO_API_KEYS;
  return env ? env.split(",").map((s) => s.trim()) : DEFAULT_API_KEYS;
}

interface CapiwsPayload {
  plugin?: string;
  name: string;
  arguments?: unknown[];
}

/** Один запрос к локальному клиенту E-IMZO. */
function capiws<T = Record<string, unknown>>(
  payload: CapiwsPayload,
  timeoutMs = 30_000
): Promise<T> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const socket = new WebSocket(CAPIWS_URL);
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        socket.close();
        reject(new Error("E-IMZO не отвечает"));
      }
    }, timeoutMs);

    socket.onopen = () => socket.send(JSON.stringify(payload));
    socket.onerror = () => {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        reject(new Error("E-IMZO не запущен"));
      }
    };
    socket.onmessage = (event) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      socket.close();
      try {
        const data = JSON.parse(event.data);
        if (data.success === false || data.reason) {
          reject(new Error(data.reason ?? "Ошибка E-IMZO"));
        } else {
          resolve(data as T);
        }
      } catch {
        reject(new Error("Некорректный ответ E-IMZO"));
      }
    };
  });
}

export interface EimzoCertificate {
  disk: string;
  path: string;
  name: string;
  alias: string;
  // Распарсенные поля alias
  cn: string;
  organization: string | null;
  tin: string | null;
  serialNumber: string | null;
  validTo: string | null;
}

function parseAlias(raw: {
  disk: string;
  path: string;
  name: string;
  alias: string;
}): EimzoCertificate {
  const fields: Record<string, string> = {};
  for (const part of raw.alias.split(",")) {
    const idx = part.indexOf("=");
    if (idx > 0) {
      fields[part.slice(0, idx).trim().toLowerCase()] = part.slice(idx + 1).trim();
    }
  }
  return {
    ...raw,
    cn: fields["cn"] ?? raw.name,
    organization: fields["o"] || null,
    tin: fields["1.2.860.3.16.1.1"] || fields["uid"] || null,
    serialNumber: fields["serialnumber"] || null,
    validTo: fields["validto"] || null,
  };
}

/** Установлен ли и запущен ли клиент E-IMZO. */
export async function eimzoAvailable(): Promise<boolean> {
  try {
    await capiws({ name: "version" }, 2000);
    return true;
  } catch {
    return false;
  }
}

/** Регистрация API-ключей домена (обязательный первый вызов сессии). */
export async function eimzoInit(): Promise<void> {
  await capiws({ name: "apikey", arguments: apiKeys() }, 5000);
}

/** Ключи (сертификаты) пользователя со всех дисков. */
export async function listCertificates(): Promise<EimzoCertificate[]> {
  const result = await capiws<{
    certificates: { disk: string; path: string; name: string; alias: string }[];
  }>({ plugin: "pfx", name: "list_all_certificates" });
  return (result.certificates ?? []).map(parseAlias);
}

/** Подписывает строку (хеш контракта) выбранным ключом. Пароль ключа
 *  запрашивает сам клиент E-IMZO. Возвращает PKCS#7 в base64. */
export async function signWithCertificate(
  cert: EimzoCertificate,
  content: string
): Promise<{ pkcs7: string; serial: string | null }> {
  const loaded = await capiws<{ keyId: string }>({
    plugin: "pfx",
    name: "load_key",
    arguments: [cert.disk, cert.path, cert.name, cert.alias],
  });
  const data64 =
    typeof window !== "undefined"
      ? window.btoa(unescape(encodeURIComponent(content)))
      : "";
  const signed = await capiws<{
    pkcs7_64: string;
    signer_serial_number?: string;
  }>(
    {
      plugin: "pkcs7",
      name: "create_pkcs7",
      arguments: [data64, loaded.keyId, "no"],
    },
    120_000 // пользователь вводит пароль в окне E-IMZO
  );
  return {
    pkcs7: signed.pkcs7_64,
    serial: signed.signer_serial_number ?? cert.serialNumber,
  };
}
