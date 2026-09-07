# Vodič za instalaciju — HM Digital i CEZIH

**Za korisnike (ordinacije i poliklinike) — postavite sve što trebate za rad s CEZIH-om u 5 koraka.**

Cijela instalacija traje otprilike 20–30 minuta. Potrebno je napraviti **samo jednom**, na svakom računalu s kojeg ćete raditi. Ako zapnete, javite nam se — kontakt je na dnu.

---

## Što vam treba prije početka

| Što | Napomena |
|---|---|
| Računalo sa Windows 10 ili 11 (64-bit) | |
| Čitač pametnih kartica (USB) | Bilo koji čitač s oznakom CCID / ISO 7816 |
| Vaša Certilia kartica | Kartica koju ste dobili za elektroničko potpisivanje |
| PIN kartice | Dobijete ga s karticom (5 znamenki) |
| Pristupni podaci za HM Digital | Email i lozinka koje ste dobili od nas |

**Preporučeni redoslijed je važan** — instalirajte sve navedeno redom po koracima.

---

## Korak 1 — Certilia Middleware (softver za karticu)

Bez ovog softvera Windows ne prepoznaje certifikat s vaše kartice.

1. Otvorite **https://www.certilia.com/preuzimanja**
2. Preuzmite **Certilia Middleware** za Windows (trenutna verzija: 3.9.10)
3. Pokrenite instalaciju i pratite čarobnjaka (*Dalje → Dalje → Kraj*)
4. Ako vas računalo pita za dozvolu administratora — odobrite
5. **Umetnite karticu u čitač** nakon instalacije

> Nakon instalacije Windows automatski uvozi certifikat s kartice. Ako se certifikat ne pojavi, na istoj stranici Certilije postoji članak "Uvoz certifikata s kartice nije uspio – Windows".

## Korak 2 — Cisco AnyConnect (VPN za pristup CEZIH-u)

1. Otvorite **https://www.cezih.hr** → lijevi izbornik → **VPN klijent**
   (izravna poveznica: http://www.cezih.hr/VPN_klijent.html)
2. Preuzmite klijentsku aplikaciju za Windows 10 i 11
3. Instalirajte je (zadržite zadane opcije)
4. **Na istoj stranici** preuzmite i **korijenski certifikat HZZO**:
   dvoklik na preuzetu datoteku → *Otvori* → **Instaliraj certifikat…** → *Dalje → Dalje → Kraj*

> Napomena: stranica cezih.hr ponekad pokazuje sigurnosnu upozorujuću poruku u pregledniku (njihov je certifikat drugačiji). To je normalno — nastavite preuzimanje.

## Korak 3 — HM Digital Agent (naša lokalna aplikacija)

1. Otvorite **https://github.com/disjohndoe/agent/releases** i preuzmite najnoviji instalacijski program (datoteka koja završava na `-setup.exe`)
2. Instalirajte i pokrenite ga — aplikacija sjedi u traci uz sat (donji desni kut)
3. Agent se **sam ažurira** — ne morate nikad više ništa instalirati

## Korak 4 — Spajanje na VPN

1. Umetnite karticu u čitač
2. Pokrenite **Cisco AnyConnect**
3. Adresa poslužitelja: **`pvpri.cezih.hr`**
4. Kliknite *Connect* — ponudit će certifikat s vaše kartice
5. Unesite **PIN kartice**
6. VPN je spojen kada ikona pokazuje zaključanicu

> PIN se unosi **jednom po sesiji**. Ako ne radite ~30 minuta, VPN se sam odspoji — ponovno spojite istim postupkom.

## Korak 5 — Prijava u HM Digital i povezivanje agenta

1. Otvorite **https://app.hmdigital.hr** i prijavite se svojim podacima
2. Na stranici **CEZIH** kliknite gumb za **povezivanje agenta** — aplikacija će se sama povezati
3. U **Postavke > Korisnici** kliknite **"Poveži karticu"** — time se vaš korisnički račun veže na vašu karticu (to se radi jednom)

## Provjera da sve radi

Na stranici **CEZIH** u aplikaciji sve tri lampice trebaju biti **zelene**:
- ✅ Cloud (agent povezan)
- ✅ VPN
- ✅ Kartica

Zatim isprobajte **"Provjera osiguranja"** — upišite MBO broj bolesnika i kliknite *Provjeri*. Ako se prikažu podaci bolesnika — sve radi.

---

## Česte poteškoće

| Problem | Rješenje |
|---|---|
| Cisco javlja grešku s certifikatom | Nije instaliran **Certilia Middleware** (Korak 1) ili kartica nije u čitaču |
| Kartica se ne prepoznaje | Izvadite karticu, očistite zlatne kontakte suhom krpom, umetnite čvrsto; probajte drugi USB priključak |
| VPN se odspojio | Normalno nakon ~30 min mirovanja — spojite ponovno (PIN ponovno) |
| Agent "bljeska" crnim prozorima | Stara verzija — ažurirat će se sam; ili instalirajte najnoviju s GitHuba (Korak 3) |
| Certilia (potpis na mobitelu) umjesto kartice | Moguće u Postavke > Korisnici — ali kartica i dalje treba biti u čitaču za VPN |

## Podrška

Za pomoć oko instalacije javite se našem timu — rado ćemo proći korake s vama putem daljinskog pristupa.
