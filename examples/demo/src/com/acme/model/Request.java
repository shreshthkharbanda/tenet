package com.acme.model;

public final class Request {
  private String cardNumber;
  private String cardExpiry;
  private String cardCvv;
  private String bankAccount;
  private String bankRouting;
  private String bankOwner;

  public Request(String cardNumber, String cardExpiry, String cardCvv) {
    this.cardNumber = cardNumber;
    this.cardExpiry = cardExpiry;
    this.cardCvv = cardCvv;
  }

  public Request(String bankAccount, String bankRouting, String bankOwner, int unusedMarker) {
    this.bankAccount = bankAccount;
    this.bankRouting = bankRouting;
    this.bankOwner = bankOwner;
  }

  public String summary() {
    return cardNumber + cardExpiry + cardCvv + bankAccount + bankRouting + bankOwner;
  }
}
