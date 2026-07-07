import type { Metadata } from "next";
// Шрифты лежат в node_modules (fontsource), а не тянутся с Google при
// сборке — fonts.googleapis.com из локальной сети недоступен
import "@fontsource-variable/manrope";
import "@fontsource-variable/work-sans";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "AI Legal Workspace",
  description: "Управление контрактами и анализ рисков для юридического отдела",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" suppressHydrationWarning className="h-full antialiased">
      <head>
        {/* Тема до первой отрисовки — без мигания светлым */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
