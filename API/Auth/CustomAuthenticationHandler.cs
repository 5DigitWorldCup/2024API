using API.Services.Interfaces;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;
using System.Security.Claims;
using System.Text.Encodings.Web;

namespace API.Auth;

public class CustomAuthenticationHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
	private readonly ISessionsService _sessionsService;

	public CustomAuthenticationHandler(
		IOptionsMonitor<AuthenticationSchemeOptions> options,
		ILoggerFactory logger,
		UrlEncoder encoder,
		ISystemClock clock,
		ISessionsService sessionsService)
		: base(options, logger, encoder, clock)
	{
		_sessionsService = sessionsService;
	}

	protected override async Task<AuthenticateResult> HandleAuthenticateAsync()
	{
		// Extract the token from the Authorization header
		string? authToken = Request.Headers["Authorization"];
		if (string.IsNullOrEmpty(authToken))
		{
			return AuthenticateResult.Fail("Missing Authorization header");
		}

		var principal = await AuthenticateAsync(authToken);
		if (principal == null)
		{
			return AuthenticateResult.Fail("Invalid token");
		}

		var ticket = new AuthenticationTicket(principal, Scheme.Name);
		return AuthenticateResult.Success(ticket);
	}

	public async Task<ClaimsPrincipal?> AuthenticateAsync(string sessionToken)
	{
		var registrant = await _sessionsService.GetRegistrantAsync(sessionToken);
		if (registrant == null)
		{
			return null;
		}

		var claims = new List<Claim>
		{
			new(ClaimTypes.NameIdentifier, registrant.OsuId.ToString()),
			new(ClaimTypes.Name, registrant.OsuName)
		};

		var identity = new ClaimsIdentity(claims, "Registrant");
		return new ClaimsPrincipal(identity);
	}
}