const REPO = "https://github.com/andygolubev/nebius-serverless-challenge-2026";

export function Terms() {
  return (
    <div className="static-page terms-page">
      <section className="static-hero">
        <div className="static-hero-inner">
          <p className="eyebrow">Terms of use · Nebius Serverless Challenge 2026</p>
          <h1>The short version</h1>
          <p className="lede">
            Eight points, plain language, no lawyers involved. If something here matters to you, read
            it before you sign in.
          </p>
        </div>
      </section>

      <section className="static-body">
        <div className="terms-list">
          {TERMS.map((term, index) => (
            <div className={`terms-item${term.highlight ? " highlight" : ""}`} key={term.title}>
              <span className="num">{String(index + 1).padStart(2, "0")}</span>
              <h2>{term.title}</h2>
              <p>{term.body}</p>
            </div>
          ))}
        </div>
        <p className="terms-close">Be happy and enjoy your day.</p>
        <p className="terms-updated">Last updated 2 August 2026 · Andy Golubev</p>
      </section>
    </div>
  );
}

const TERMS = [
  { title: "Who made this", highlight: false, body: <>I am the creator: <strong>Andy Golubev</strong>. Sim2Policy is my personal project for the Nebius Serverless Challenge 2026 — not a company, not a product.</> },
  { title: "The results are yours", highlight: false, body: <>Anything trained on this site — policies, checkpoints, metrics, videos — can be used by anyone, for anything. No licence to ask for, no attribution required.</> },
  { title: "No guarantees at all", highlight: false, body: <>I do not promise that training works, that it keeps working, or that any result is correct. Everything here is provided as is. You use it at your own risk.</> },
  { title: "I am not responsible for what you do with it", highlight: false, body: <>That includes harmful use. What you train and where you deploy it is your decision and your responsibility. These are simulator-only policies and are not directly deployable to physical hardware.</> },
  { title: "Your email, and only your email", highlight: false, body: <>I use it for one thing: creating your personal space so your training results have somewhere to live. No marketing, no sharing, no selling. It is erased when this project ends — by the end of 2026, possibly sooner.</> },
  { title: "Download your results early", highlight: true, body: <>I do not guarantee storage of anything you train. Files can disappear when the project ends or before that. Please download what you care about as soon as it is ready.</> },
  { title: "Open source", highlight: false, body: <>The whole thing is on GitHub — read it, run it, fork it: <a href={REPO} target="_blank" rel="noreferrer">github.com/andygolubev/nebius-serverless-challenge-2026</a></> },
  { title: "These terms can change", highlight: false, body: <>Without notice — I have probably forgotten something important and will add it later. Sorry about that.</> },
];
