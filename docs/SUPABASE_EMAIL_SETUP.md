# Supabase email delivery setup

**Status: BLOCKED — USER CONFIGURATION REQUIRED.** PharmaOne handles email throttling and has confirmation and password-reset pages, but the project has not been configured with a verified custom SMTP sender and a delivered confirmation/reset email has not been inspected. Do not disable email confirmation as a workaround.

Supabase's default mail service is restricted and currently allows only a small number of messages per hour. Follow the [custom SMTP guide](https://supabase.com/docs/guides/auth/auth-smtp) and [rate-limit guide](https://supabase.com/docs/guides/auth/rate-limits) for current limits.

## Dashboard steps

1. Choose an SMTP provider such as Resend or Brevo and verify a domain you control. Create a sender address such as `no-reply@auth.example.com`. Configure the provider's SPF, DKIM, and DMARC DNS records; wait for its verification status before using the sender.
2. In the Supabase project, open **Authentication → SMTP Settings**. Enable custom SMTP and enter the provider's **host**, **port**, **username**, **password**, verified sender address, and sender name. Keep these credentials only in Supabase and your password manager; never place them in `web/.env.local` or the repo.
3. In **Authentication → Providers → Email**, keep email confirmation enabled. Review the **Confirm signup** and **Reset password** templates. Keep Supabase's confirmation URL/token variables intact.
4. In **Authentication → URL Configuration**, set the local Site URL to the address you will actually use, then add exact allowed redirects for both local hostnames: `http://localhost:3000/onboarding/pharmacy`, `http://127.0.0.1:3000/onboarding/pharmacy`, `http://localhost:3000/reset-password`, and `http://127.0.0.1:3000/reset-password`. Add the HTTPS production equivalents only when a real domain is deployed. See [redirect URL configuration](https://supabase.com/docs/guides/auth/redirect-urls).
5. In **Authentication → Rate Limits**, choose a sending limit that the SMTP plan can support. Account for confirmation and password-reset emails together. Do not simply raise the limit beyond the provider's quota.
6. Use one disposable inbox to test signup and confirmation. Open the email once, confirm, and sign in. Then request one password reset, open its link, set a new password, and sign in again. Verify that repeated form clicks do not send repeated email requests and that a throttled request displays the wait guidance.

The app's signup form sends users to `/onboarding/pharmacy` after confirmation. Password recovery sends users to `/reset-password`, where they enter a new password. The UI never stores an SMTP password. Supabase's [password flow](https://supabase.com/docs/guides/auth/passwords) requires these redirect URLs to be allowlisted.
