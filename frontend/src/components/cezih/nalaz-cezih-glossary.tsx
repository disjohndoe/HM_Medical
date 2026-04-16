export function NalazCezihGlossary() {
  return (
    <div className="space-y-2 text-xs leading-relaxed">
      <p>
        <span className="font-semibold text-foreground">Nalaz</span>
        <span className="text-muted-foreground"> — zapis u lokalnoj evidenciji klinike.</span>
      </p>
      <p>
        <span className="font-semibold text-foreground">e-Nalaz</span>
        <span className="text-muted-foreground">
          {" "}
          — isti nalaz nakon uspješnog slanja na CEZIH (državni zdravstveni sustav). Tek tada postaje vidljiv drugim ustanovama i pacijentu preko Portala zdravlja.
        </span>
      </p>
    </div>
  )
}
