$(function()
{
  var updateUptime = function(elm, t)
  {
    var $e = $(elm),
        up = $e.data("time");
    if(!up) return;
    $e.text(fmtTime(t - up));
  };

  var updateUptimes = function()
  {
    var now = Math.floor(+(new Date) / 1000);
    uptimes.each(function()
    {
      updateUptime(this, now);
    });
  };

  var fmtTime = function(t)
  {
    t = +t;
    var hours = Math.floor(t / 3600) % 3600,
        minutes = Math.floor(t / 60) % 60,
        seconds = Math.floor(t % 60)

    return ([hours, minutes, seconds]).map(function(u)
    {
       return ("00" + u).substr(-2);
    }).join(':');
  };

  var uptimes = $(".uptime");
  setInterval(updateUptimes, 333);
});
