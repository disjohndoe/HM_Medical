"use client";

export default function GlobalError({
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <html lang="hr">
      <body className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900">
            Neočekivana greška
          </h1>
          <p className="mt-2 text-gray-600">
            Došlo je do neočekivane greške. Molimo pokušajte ponovo.
          </p>
          <button
            onClick={() => unstable_retry()}
            className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
            Pokušaj ponovo
          </button>
        </div>
      </body>
    </html>
  );
}
