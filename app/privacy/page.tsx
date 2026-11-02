export default function PrivacyPolicy() {
  return (
    <main className="max-w-3xl mx-auto px-4 py-12 space-y-6 text-gray-800">
      <h1 className="text-4xl font-bold mb-8">Privacy Policy</h1>
      
      <p className="text-sm text-gray-500">Last updated: November 2026</p>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold mt-8">1. Introduction</h2>
        <p>
          Welcome to SocialArtzy ("we", "our", or "us"). This Privacy Policy explains how our custom 
          automation bot handles information when you use our website and services.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold mt-8">2. Information We Collect</h2>
        <p>
          Our application is a personal automation tool designed to post artwork. We do not collect, 
          store, or share any personal data from visitors to this website.
        </p>
        <p>
          When interacting with third-party platforms (such as Pinterest or Instagram) via our bot, 
          we only use API keys and access tokens authorized by the account owner to publish content. 
          We do not store these tokens in an unencrypted or publicly accessible manner.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold mt-8">3. Third-Party Services</h2>
        <p>
          Our service integrates with Pinterest and Instagram. By using our service, you acknowledge 
          that data (such as images and captions) will be transmitted to these platforms in accordance 
          with their respective Privacy Policies.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold mt-8">4. Contact Us</h2>
        <p>
          If you have any questions about this Privacy Policy, please contact us at: 
          <strong> your-email@example.com</strong> (Replace this with your actual email address).
        </p>
      </section>
    </main>
  );
}
