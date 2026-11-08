# Accounts and access

## Creating an account

Anyone can create a DataPact account from the sign-up page by choosing a username and a password. No email address is required and no invitation is needed, which is deliberate: the system is meant to be easy for a reviewer or a new team member to get into. Password strength is checked when the account is created, so very short, entirely numeric or very common passwords are rejected with an explanation. Creating an account gives immediate access to every page in the application. There are no permission tiers, so a new account can see the same datasets and reports as an established one.

## Signing in with Google

As well as a username and password, DataPact supports signing in with a Google account. The Continue with Google button appears on both the login and sign-up pages, and the flow hands the account straight back to the application once Google confirms it. Google sign-in and password sign-in are alternatives rather than a sequence, so an account created one way does not need the other. If Google credentials have not been configured in the environment the button is replaced by a short note, and password sign-in continues to work normally, so a missing configuration never locks anybody out.

## What anonymous visitors can see

Signed-out visitors see the home page, the login and sign-up pages, and nothing else. The navigation hides every protected link while you are signed out, so the menu describes what the visitor can actually do rather than offering doors that are locked. Hiding the links is a courtesy, not the security boundary: typing a protected address directly still redirects to the login page, because the protection lives in the view rather than in the menu. The home page also points anonymous visitors at the one endpoint that is public on purpose.

## Protected and public endpoints

DataPact draws a deliberate line between its endpoints. The run-outcome summary is public: it returns three aggregate counts and no file names, dataset names or usernames, so it can be read without an account and used for charts or demonstrations. Every other endpoint requires a session. Protected pages redirect a signed-out browser to the login screen, which is the right behaviour for a person. Protected data endpoints instead return an unauthorised status with a short message, because a program calling an endpoint needs a clear refusal rather than a login page it cannot read.
