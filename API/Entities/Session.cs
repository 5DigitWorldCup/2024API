using Dapper;

namespace API.Entities;

[Table("sessions")]
public class Session : EntityBase
{
	[Column("osu_id")]
	public long OsuId { get; set; }
	
	[Column("token")]
	public string Token { get; set; } = null!;
	
	[Column("expiration")]
	public DateTime Expiration { get; set; }
}