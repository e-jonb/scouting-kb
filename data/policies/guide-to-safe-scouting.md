---
source: https://www.scouting.org/health-and-safety/gss/
fetched: 2026-03-03
bsa_version: 2026.Q1
note: "Full PDF available at scouting.org. This file captures the web summary pages."
---

# Guide to Safe Scouting — Overview

_Overview of the Guide to Safe Scouting (GSS). The GSS is BSA's primary policy document covering all aspects of safe unit operation._

> **Note:** Full PDF available at scouting.org. This file captures the web summary pages.

[![](https://www.scouting.org/wp-content/uploads/2022/03/scouting-stacked-logo-white@2x.webp)](/)

[![](https://www.scouting.org/wp-content/uploads/2026/01/a-250-scouting-america-250-color-logo@2x.webp)![](data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%20118%2096%22%3E%3C/svg%3E)](/service/)

[My.scouting](https://my.scouting.org/)

* [Give](https://give.scouting.org/a/support-military-families)
* [Scout shop](https://www.scoutshop.org/)
* [Be a scout](https://beascout.scouting.org/?utm_source=scouting&utm_medium=join_header&utm_campaign=ongoing)
* [Programs](https://www.scouting.org/programs/)
  + [Cub Scouts](https://www.scouting.org/programs/cub-scouts/)
  + [Scouts BSA](https://www.scouting.org/programs/scouts-bsa/)
  + [Venturing](https://www.scouting.org/programs/venturing/)
  + [Sea Scouts](https://seascout.org/)
  + [Exploring](https://www.exploring.org/)
* [Scouting Safely](https://www.scouting.org/health-and-safety/)
  + [Scouts First Helpline (1-844-SCOUTS1)](https://www.scouting.org/training/youth-protection/#hotlink)
  + [Guide to Safe Scouting](https://www.scouting.org/health-and-safety/gss/)
  + [Youth Protection](https://www.scouting.org/health-and-safety/youth-protection/)
  + [Incident Reporting](https://www.scouting.org/health-and-safety/gss/gss14/)
  + [Safety Moments](https://www.scouting.org/health-and-safety/safety-moments/)
  + [Annual Health & Medical Record](https://www.scouting.org/health-and-safety/ahmr/)
* [Awards](https://www.scouting.org/awards/)
  + [Awards Central](https://www.scouting.org/awards/awards-central/)
  + [Scholarships](https://www.scouting.org/awards/scholarships/)
  + [Outdoor Ethics Awards](https://www.scouting.org/awards/awards-central/outdoor-ethics-awards/)
  + [Guide to Awards & Insignia](https://www.scouting.org/resources/insignia-guide/)
* [About](https://www.scouting.org/about/)
  + [Careers](https://www.scouting.org/careers/)
  + [Find a Local Council](https://www.scouting.org/about/local-council-locator/)
  + [Scouting Newsroom](https://scoutingnewsroom.org/)
  + [Contact Us](https://www.scouting.org/about/contact-us/)
* [Training](https://www.scouting.org/training/)
  + [Youth Training](https://www.scouting.org/training/youth/)
* [Resources](https://www.scouting.org/resources/)
  + [Commissioners](https://www.scouting.org/commissioners/)
  + [Eagle Workbook](https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/eagle-scout-workbook/)
  + [Special Needs & Disabilities](https://www.scouting.org/resources/disabilities-awareness/)
  + [International Scouting](https://www.scouting.org/international/)
  + [Council Support](https://www.scouting.org/council-support/)
  + [Scouting Wire](https://scoutingwire.org/)
  + [Recruitment](https://www.scouting.org/recruitment/)
* [Outdoor Programs](https://www.scouting.org/outdoor-programs/)
* [Merit Badges](https://www.scouting.org/skills/merit-badges/)
* [High Adventure](https://www.scouting.org/national-high-adventure-bases/)
  + [High Adventure Treks](https://www.scouting.org/national-high-adventure-bases/adventure-treks/)
  + [High Adventure Base Jobs](https://www.scouting.org/national-high-adventure-bases/jobs/)
  + [Family Adventure Camp](https://www.scouting.org/national-high-adventure-bases/family-adventure-camp/)
* [Partners](https://www.scouting.org/partnerwithus/)

const $searchBtnMobile = $('#search-nav-mobile');
$searchBtnMobile.on("click", function(e){
e.preventDefault();
$searchBtnMobile.addClass("btn-secondary");
const $input = $(".nav-search-input-mobile");
const value = $.trim($input.val());
if (value !== '') {
$input.closest("form")[0].requestSubmit();
}
});

//Change chevron orientation mobile menu
$("#menu-mobile-primary-nav-2023 > li > a.pp-menu-item").on("click", function(e) {
//Do not trigger if the actual link to parent is clicked - A tag
//Just the I or SPAN
if("I" == e.target.nodeName || "SPAN" == e.target.nodeName) {
let itag = $( this ).find("i");
if($( itag ).hasClass('fa-chevron-down')) {
$( itag ).removeClass('fa-chevron-down');
$( itag ).addClass('fa-chevron-up');
}
else {
$( itag ).removeClass('fa-chevron-up')
$( itag ).addClass('fa-chevron-down');
}
}
});
$("#menu-mobile-toggle").on("click",function(){
if($("#menu-mobile-toggle .pp-menu-toggle").hasClass("pp-active") ){
$("#menu-mobile-container").addClass("dropdown-menu-scrolling");
$("#formtoseachmobile").show();
}
else{
$("#menu-mobile-container").removeClass("dropdown-menu-scrolling");
$("#formtoseachmobile").hide();
}
});
