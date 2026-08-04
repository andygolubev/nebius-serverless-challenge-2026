// Reference implementation for saas/frontend/src/views/About.tsx (new, static page).
// Design reference: "About Me v2 light.dc.html". Footer is shared — see App.tsx.

export function About() {
  return (
    <div className="static-page">
      <section className="static-hero">
        <div className="static-hero-inner">
          <p className="eyebrow">About me</p>
          <h1>Andy Golubev</h1>
          <p className="lede">
            I built Sim2Policy on my own for the Nebius Serverless Challenge 2026 — simulation,
            training, storage, the API, the deployment and this website.
          </p>
          <div className="hero-actions">
            {LINKS.map((link, index) => (
              <a
                key={link.href}
                className={index === 0 ? "btn" : "btn btn-ghost"}
                href={link.href}
                target="_blank"
                rel="noreferrer"
              >
                {link.action}
              </a>
            ))}
          </div>
        </div>
      </section>

      <div className="static-body">
        <div className="hr" />
        <div className="about-cols">
          <p className="band-label">Why this project exists</p>
          <div style={{ display: "grid", gap: 24 }}>
            <p className="lead">
              Training robot locomotion policies normally needs hardware, patience and a lab. It
              should need neither a robot nor a budget to start — a simulator, a serverless GPU and
              durable storage are enough.
            </p>
            <p>
              So Sim2Policy trains policies in MuJoCo with PPO, runs the training as a serverless AI
              job, and keeps every result — checkpoint, metrics and a rollout video — in object
              storage that outlives the machine. Seven verified runs are published so you can judge
              the thing before you sign in, and the whole source tree is on GitHub.
            </p>
            <p>
              It is free for you to use. I am not selling anything here and I do not want your credit
              card — only an email address, so your trained robots have somewhere to live.
            </p>
          </div>
        </div>
      </div>

      <section className="showcase-band">
        <div className="showcase-band-inner">
          <p className="band-label">Find me</p>
          <div className="band-cols find-me">
            {LINKS.map((link) => (
              <a key={link.href} href={link.href} target="_blank" rel="noreferrer">
                <h3>{link.title}</h3>
                <p>{link.label}</p>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="credit">
        <div className="credit-inner">
          <p className="credit-label">Built with passion and love</p>
          <p className="credit-statement">
            Simulation, training, storage, deployment and this page — built in weeks by one person
            with an LLM. That is the time we live in, and I loved every hour of it.
          </p>
        </div>
      </section>
    </div>
  );
}

const LINKS = [
  {
    title: "Personal site",
    label: "andygolubev.com",
    action: "andygolubev.com →",
    href: "https://andygolubev.com/",
  },
  {
    title: "LinkedIn",
    label: "linkedin.com/in/andy-golubev",
    action: "LinkedIn",
    href: "https://www.linkedin.com/in/andy-golubev/",
  },
  {
    title: "Source code",
    label: "github.com/andygolubev/nebius-serverless-challenge-2026",
    action: "GitHub repository",
    href: "https://github.com/andygolubev/nebius-serverless-challenge-2026",
  },
];
