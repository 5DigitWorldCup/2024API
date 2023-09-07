using System.Security.Cryptography;
using System.Text;

namespace API.Auth;

public class HashUtilities
{
	public static bool VerifySecret(string secret, string hash)
	{
		// Hash secret using SHA256, compare against hash
		using var sha256 = SHA256.Create();
		var secretHash = sha256.ComputeHash(Encoding.UTF8.GetBytes(secret));
		var secretHashString = Convert.ToBase64String(secretHash);
		return secretHashString == hash;
	}
}