import type { Metadata } from "next";
import { Manrope, Work_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin", "cyrillic"],
});

const workSans = Work_Sans({
  variable: "--font-worksans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Legal Workspace",
  description: "Операционная система юридического отдела",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ru"
      className={`${manrope.variable} ${workSans.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
