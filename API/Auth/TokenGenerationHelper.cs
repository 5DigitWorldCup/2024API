using System.Security.Cryptography;

namespace API.Auth;

public static class TokenGenerationHelper
{
	public static string GenerateToken()
	{
		var rng = RandomNumberGenerator.Create();
		byte[] bytes = new byte[32];
		rng.GetBytes(bytes);
		return Convert.ToBase64String(bytes);
	}
}